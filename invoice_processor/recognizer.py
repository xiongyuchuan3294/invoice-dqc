"""
发票识别器 - OCR识别发票信息
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import InvoiceInfo, InvoiceType
from config import COMPANY_INFO, INVOICE_TYPES


class InvoiceRecognizer:
    """发票识别器"""

    PARTY_NAME_PATTERN = re.compile(
        r"([\\u4e00-\\u9fffA-Za-z0-9（）()·\\-]{2,}?"
        r"(?:股份有限公司|有限责任公司|有限公司|分公司|个体工商户|银行|餐饮店|餐厅|饭店|门店|酒店|超市|商行|中心|公司|店))"
    )

    # 正则表达式模式
    PATTERNS = {
        "invoice_code": r"发票代码[：:]\s*(\d+)",
        "invoice_number": r"发票号码[：:]\s*(\d+)",
        "invoice_date": r"开票日期[：:]\s*(\d{4})[年\-](\d{1,2})[月\-](\d{1,2})",
        # 不含税金额 - 优先从"合 计 ¥xxx ¥xx"格式提取
        "amount": r"合\s*计\s*[^¥]*¥\s*([\d,]+\.?\d*)",
        # 备选：标准格式"金额（小写）"
        "amount_standard": r"[^税]金额[（\(]小写[）\)][^¥]*¥?\s*([\d,]+\.?\d*)",
        # 价税合计（含税，仅作参考）
        "total_amount": r"价税合计[（\(]小写[）\)][^¥]*¥?\s*([\d,]+\.?\d*)",
        # 税额 - 从"合 计 ¥xxx ¥xx"格式提取（第二个金额）
        "tax_amount": r"合\s*计\s*[^¥]*¥\s*[\d,]+\.?\d*\s*¥\s*([\d,]+\.?\d*)",
        # 备选：税额标准格式"税额（小写）"
        "tax_amount_standard": r"税额[（\(]小写[）\)][^¥]*¥?\s*([\d,]+\.?\d*)",
        # 注意：PDF格式可能是分行的，如 "购\n名称：xxx"
        "seller_name": r"销售方名称[：:]\s*([^\n]+?)(?:\s*销|\s*$|名称)",
        "seller_tax_id": r"销售方[^\n]*统一社会信用代码/纳税人识别号[：:]\s*([A-Z0-9]+)",
        "buyer_name": r"购买方名称[：:]\s*([^\n]+?)(?:\s*购|\s*$|名称)",
        "buyer_tax_id": r"购买方[^\n]*统一社会信用代码/纳税人识别号[：:]\s*([A-Z0-9]+)",
        "items": r"货物或应税劳务、服务名称[：:]?\s*([^\n]+)",
    }
    DATE_PATTERNS = [
        r"(20\d{2})\D+(\d{1,2})\D+(\d{1,2})",
        r"(20\d{2})[./\-](\d{1,2})[./\-](\d{1,2})",
    ]

    def __init__(self):
        """初始化识别器"""
        pass

    def recognize(self, file_path: str) -> InvoiceInfo:
        """
        识别发票

        Args:
            file_path: 发票文件路径

        Returns:
            InvoiceInfo: 发票信息
        """
        file_path = Path(file_path)
        text = self._extract_text(file_path)

        invoice = InvoiceInfo(
            file_path=str(file_path),
            original_name=file_path.name,
        )

        # 提取基本信息
        invoice.invoice_code = self._extract_field(text, self.PATTERNS["invoice_code"])
        invoice.invoice_number = self._extract_field(text, self.PATTERNS["invoice_number"])
        invoice.invoice_date = self._extract_date(text)

        # 提取购销方信息（特殊处理PDF格式）
        buyer_info, seller_info = self._extract_buyer_seller_info(text)
        invoice.buyer_name = buyer_info.get("name")
        invoice.buyer_tax_id = buyer_info.get("tax_id")
        invoice.seller_name = seller_info.get("name")
        invoice.seller_tax_id = seller_info.get("tax_id")

        # 提取金额
        # 优先提取不含税金额（用于报销）
        invoice.amount = self._extract_amount(text, "amount")
        # 如果没找到，尝试标准格式
        if invoice.amount == 0:
            invoice.amount = self._extract_amount(text, "amount_standard")
        # 价税合计（含税金额，仅作记录和验证）
        invoice.total_amount = self._extract_amount(text, "total_amount")
        # 税额（用于验证）
        invoice.tax_amount = self._extract_amount(text, "tax_amount")
        if invoice.tax_amount == 0:
            invoice.tax_amount = self._extract_amount(text, "tax_amount_standard")
        # 如果没有不含税金额，才用价税合计
        if invoice.amount == 0:
            invoice.amount = invoice.total_amount

        # 提取货物/服务名称
        invoice.items = self._extract_items(text)

        # 识别发票类型
        invoice.invoice_type = self._classify_type(invoice)

        return invoice

    def _extract_text(self, file_path: Path) -> str:
        """
        从文件中提取文本

        Args:
            file_path: 文件路径

        Returns:
            str: 提取的文本
        """
        # 优先尝试 pdfplumber 处理 PDF
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                return text
        except ImportError:
            pass
        except Exception:
            pass

        # 备选：使用 PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            pass
        except Exception:
            pass

        # 如果是图片文件，需要 OCR
        # 这里简化处理，返回空字符串
        return ""

    def _extract_field(self, text: str, pattern: str) -> Optional[str]:
        """提取字段"""
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    def _extract_amount(self, text: str, field: str) -> float:
        """提取金额"""
        pattern = self.PATTERNS.get(field, r"¥?\s*([\d,]+\.?\d*)")
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            try:
                return float(match.group(1).replace(",", ""))
            except (ValueError, IndexError):
                pass
        return 0.0

    def _extract_date(self, text: str) -> Optional[datetime]:
        """
        Extract date with progressive fallback:
        1) prefer explicit invoice-date field;
        2) then prefer date near tax-authority keyword;
        3) finally fallback to first valid date in full text.
        """
        # 1) Explicit invoice-date field first.
        match = re.search(self.PATTERNS["invoice_date"], text, re.MULTILINE)
        parsed = self._parse_date_match(match)
        if parsed:
            return parsed

        # 2) Prefer date near tax authority keyword.
        near_tax_authority = self._extract_date_near_keyword(
            text,
            "\u56fd\u5bb6\u7a0e\u52a1\u603b\u5c40",
        )
        if near_tax_authority:
            return near_tax_authority

        # 3) Final fallback: first valid date in full text.
        return self._extract_any_date(text)

    def _parse_date_match(self, match: Optional[re.Match]) -> Optional[datetime]:
        """Safely convert regex match groups to datetime."""
        if not match:
            return None

        try:
            year, month, day = match.groups()
            return datetime(int(year), int(month), int(day))
        except (ValueError, IndexError, TypeError):
            return None

    def _extract_any_date(self, text: str) -> Optional[datetime]:
        """Extract first valid date from a text fragment."""
        for pattern in self.DATE_PATTERNS:
            match = re.search(pattern, text, re.MULTILINE)
            parsed = self._parse_date_match(match)
            if parsed:
                return parsed
        return None

    def _extract_date_near_keyword(
        self,
        text: str,
        keyword: str,
        window: int = 120,
    ) -> Optional[datetime]:
        """Prefer a date in the neighborhood of a keyword."""
        for key_match in re.finditer(re.escape(keyword), text):
            start = max(0, key_match.start() - window)
            end = min(len(text), key_match.end() + window)
            nearby_text = text[start:end]
            parsed = self._extract_any_date(nearby_text)
            if parsed:
                return parsed
        return None

    def _extract_items(self, text: str) -> list[str]:
        """提取货物/服务名称"""
        items = []

        # 方法1: 尝试匹配表格格式 "项目名称 xxx xxx"
        # 查找以*开头的内容（如 *餐饮服务*餐饮服务）
        pattern = r'\*([^*]+)\*([^\s]+)'
        matches = re.findall(pattern, text)
        for category, name in matches:
            full_name = f"*{category}*{name}"
            if full_name and full_name not in items:
                items.append(full_name)

        # 方法2: 查找表格中的项目名称（在"项目名称"标题后的行）
        # 跳过"购/销 名称"的匹配
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if '项目名称' in line:
                # 下一行可能是实际的项目数据
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # 提取项目名称（通常在行首，以*开头）
                    if next_line.startswith('*'):
                        item_match = re.match(r'([^\s]+(?:\s+[^\s]+)*)', next_line)
                        if item_match:
                            item = item_match.group(1).strip()
                            if item and item not in items:
                                items.append(item)

        # 方法3: 直接搜索常见的服务项目格式
        # *餐饮服务*xxx, *电信服务*xxx, *交通运输*xxx 等
        service_pattern = r'\*([^\*]+服务[^\*]*)\*([^\s]+)'
        service_matches = re.findall(service_pattern, text)
        for category, name in service_matches:
            full_name = f"*{category}*{name}"
            if full_name not in items:
                items.append(full_name)

        return items

    def _extract_buyer_seller_info(self, text: str) -> tuple[dict, dict]:
        """
        提取购销方信息

        PDF格式示例：
        购 名称：深圳前海微众银行股份有限公司 销 名称：武汉市渔焰餐饮有限公司
        买 售
        方 方
        信 统一社会信用代码/纳税人识别号：9144030031977063XH 信 统一社会信用代码/纳税人识别号：91420106MAEHQMTQ7U
        息 息
        """
        buyer_info = {"name": None, "tax_id": None}
        seller_info = {"name": None, "tax_id": None}

        # 方法1: 尝试匹配标准格式（购买方名称：xxx）
        buyer_match = re.search(r"购买方[^\n]*名称[：:]\s*([^\n]+?)(?:\s+销|\s*$|\n)", text)
        if buyer_match:
            buyer_info["name"] = buyer_match.group(1).strip()

        seller_match = re.search(r"销售方[^\n]*名称[：:]\s*([^\n]+?)(?:\s*$|\n)", text)
        if seller_match:
            seller_info["name"] = seller_match.group(1).strip()

        # 方法2: 如果上面没找到，尝试匹配 "购/买/方" 这种分行格式
        if not buyer_info["name"] or not seller_info["name"]:
            # 先尝试匹配同一行中的购销方名称
            # 格式：购 名称：xxx 销 名称：yyy
            same_line_pattern = r"名称[：:]\s*([^\n]*?[公司|厂|店|心|部|务][^\n]*?)\s+销\s+名称[：:]\s*([^\n]*?[公司|厂|店|心|部|务][^\n]*?)(?:\s|$)"
            match = re.search(same_line_pattern, text)
            if match:
                buyer_info["name"] = match.group(1).strip()
                seller_info["name"] = match.group(2).strip()
            else:
                # 尝试更灵活的匹配 - 查找两个"名称："后面的内容
                # 公司名称通常以：公司、有限公司、股份、厂、店等结尾
                name_pattern = r"名称[：:]\s*([^\n]*?(?:公司|有限|股份|厂|店|心|部|务|个体工商户)[^\n]*?)(?:\s+销\s+名称|名称|买\s|售\s|方\s|$)"
                names = re.findall(name_pattern, text)
                if len(names) >= 2:
                    buyer_info["name"] = names[0].strip()
                    seller_info["name"] = names[1].strip()
                elif len(names) == 1:
                    # 只找到一个，尝试从税号后面找
                    buyer_info["name"] = names[0].strip()

        # 提取税号
        # 统一社会信用代码/纳税人识别号：税号
        tax_pattern = r"统一社会信用代码/纳税人识别号[：:]\s*([A-Z0-9]+)"
        tax_ids = re.findall(tax_pattern, text)
        if len(tax_ids) >= 2:
            buyer_info["tax_id"] = tax_ids[0]
            seller_info["tax_id"] = tax_ids[1]
        elif len(tax_ids) == 1:
            # 只有一个税号，根据上下文判断
            buyer_info["tax_id"] = tax_ids[0]

        # 备选方法：使用原始正则
        if not buyer_info["tax_id"]:
            buyer_info["tax_id"] = self._extract_field(text, self.PATTERNS["buyer_tax_id"])
        if not seller_info["tax_id"]:
            seller_info["tax_id"] = self._extract_field(text, self.PATTERNS["seller_tax_id"])

        # 方法3: 针对列式布局兜底（名称/税号分行展示）
        if (
            not buyer_info["name"]
            or not seller_info["name"]
            or not buyer_info["tax_id"]
            or not seller_info["tax_id"]
        ):
            col_buyer, col_seller = self._extract_columnar_party_info(text)
            buyer_info["name"] = buyer_info["name"] or col_buyer["name"]
            seller_info["name"] = seller_info["name"] or col_seller["name"]
            buyer_info["tax_id"] = buyer_info["tax_id"] or col_buyer["tax_id"]
            seller_info["tax_id"] = seller_info["tax_id"] or col_seller["tax_id"]

        return buyer_info, seller_info

    def _extract_columnar_party_info(self, text: str) -> tuple[dict, dict]:
        """
        Handle column-like buyer/seller blocks often seen in e-invoice PDFs:
        - one line with two organization names
        - next line with two tax IDs
        """
        buyer_info = {"name": None, "tax_id": None}
        seller_info = {"name": None, "tax_id": None}

        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            tax_ids = self._extract_tax_id_candidates(line)
            if len(tax_ids) < 2:
                continue

            buyer_info["tax_id"] = tax_ids[0]
            seller_info["tax_id"] = tax_ids[1]

            name_line = self._find_name_line_before_tax_line(lines, idx)
            if name_line:
                names = self._split_party_names(name_line)
                if len(names) >= 2:
                    buyer_info["name"], seller_info["name"] = names[0], names[1]
            break

        return buyer_info, seller_info

    def _extract_tax_id_candidates(self, text: str) -> list[str]:
        """Extract tax-id-like candidates and filter obvious false positives."""
        candidates = re.findall(r"\b[0-9A-Z]{15,20}\b", text.upper())
        ids: list[str] = []
        for item in candidates:
            # Prefer identifiers containing letters to avoid matching invoice codes.
            if not any(ch.isalpha() for ch in item):
                continue
            if item not in ids:
                ids.append(item)
        return ids

    def _find_name_line_before_tax_line(self, lines: list[str], tax_line_index: int) -> Optional[str]:
        """Search nearby previous lines for the buyer/seller name pair."""
        skip_keywords = (
            "统一社会信用代码",
            "纳税人识别号",
            "国家税务总局",
            "税务局",
            "发票",
            "监制",
            "下载次数",
            "名称：",
        )

        for offset in range(1, 6):
            idx = tax_line_index - offset
            if idx < 0:
                break

            line = lines[idx]
            if any(keyword in line for keyword in skip_keywords):
                continue
            if len(self._extract_tax_id_candidates(line)) > 0:
                continue
            if len(line) < 4:
                continue
            return line

        return None

    def _split_party_names(self, line: str) -> list[str]:
        """Split a combined 'buyer seller' line into two organization names."""
        normalized = re.sub(r"\s+", " ", line).strip()

        # First try explicit multi-space separators.
        chunks = [item.strip() for item in re.split(r"\s{2,}", line) if item.strip()]
        if len(chunks) >= 2:
            return chunks[:2]

        # Then try extracting two organization-like names.
        org_names = []
        for name in self.PARTY_NAME_PATTERN.findall(normalized):
            clean = name.strip(" ：:")
            if clean and clean not in org_names:
                org_names.append(clean)
        if len(org_names) >= 2:
            return org_names[:2]

        # Last fallback: if known buyer company appears in the line, split around it.
        buyer_name = COMPANY_INFO.get("name", "")
        if buyer_name and buyer_name in normalized:
            before, after = normalized.split(buyer_name, 1)
            before = before.strip()
            after = after.strip()
            if after:
                return [buyer_name, after]
            if before:
                return [before, buyer_name]

        return []
    def _classify_type(self, invoice: InvoiceInfo) -> InvoiceType:
        """
        分类发票类型

        Args:
            invoice: 发票信息

        Returns:
            InvoiceType: 发票类型
        """
        # 组合文本用于匹配
        text_parts = []
        text_parts.extend(invoice.items)
        if invoice.seller_name:
            text_parts.append(invoice.seller_name)

        combined_text = " ".join(text_parts).lower()

        # 按优先级检查类型
        # 1. 餐饮
        if any(kw.lower() in combined_text for kw in INVOICE_TYPES["dining"]["keywords"]):
            return InvoiceType.DINING

        # 2. 交通
        if any(kw.lower() in combined_text for kw in INVOICE_TYPES["transport"]["keywords"]):
            return InvoiceType.TRANSPORT

        # 3. 通讯
        if any(kw.lower() in combined_text for kw in INVOICE_TYPES["communication"]["keywords"]):
            return InvoiceType.COMMUNICATION

        return InvoiceType.UNKNOWN
