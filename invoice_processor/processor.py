# -*- coding: utf-8 -*-
"""
主处理器 - 协调整个处理流程
"""
from pathlib import Path

from models import SelectionResult
from recognizer import InvoiceRecognizer
from validator import InvoiceValidator
from selector import InvoiceSelector
from file_manager import FileManager
from reporter import ReportGenerator


class InvoiceProcessor:
    """发票处理器"""

    def __init__(self, invoice_pool: str, output_dir: str, month: str):
        self.invoice_pool = Path(invoice_pool)
        self.output_dir = output_dir
        self.month = month

        self.recognizer = InvoiceRecognizer()
        self.validator = InvoiceValidator(month)
        self.selector = InvoiceSelector()
        self.file_manager = FileManager(invoice_pool, output_dir, month)
        self.reporter = ReportGenerator()

    def process(self):
        """执行处理流程：仅从 invoice/ 读取，清空并重建 output/。"""
        invoice_files = self._scan_invoice_pool()

        if not invoice_files:
            print(f"未在 {self.invoice_pool} 中找到发票文件")
            result = SelectionResult(month=self.month)
            self.file_manager.ensure_directories()
            self.reporter.generate(result, self.output_dir)
            self.reporter.print_summary(result)
            return result

        print(f"找到 {len(invoice_files)} 个待处理发票文件，开始处理...")

        invoices = []
        seen_invoice_numbers = {}

        for i, file_path in enumerate(invoice_files, 1):
            print(f"[{i}/{len(invoice_files)}] 处理：{file_path.name}")

            try:
                invoice = self.recognizer.recognize(str(file_path))

                if invoice.invoice_number:
                    if invoice.invoice_number in seen_invoice_numbers:
                        existing_file = seen_invoice_numbers[invoice.invoice_number]
                        print(f"  WARNING 警告: 发票号码重复 {invoice.invoice_number}")
                        print(f"     已存在: {existing_file}")
                        print(f"     当前文件: {file_path.name}")
                        invoice.is_duplicate = True
                    seen_invoice_numbers[invoice.invoice_number] = file_path.name

                self.validator.validate(invoice)

                status_icon = "OK" if invoice.is_valid else "ERR"
                date_text = invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else "N/A"
                print(
                    f"  {status_icon} {invoice.invoice_type.name_cn} | "
                    f"金额: {invoice.amount:.2f}元 | 日期: {date_text}"
                )

                if invoice.reject_reasons:
                    print(f"  原因: {'; '.join(invoice.reject_reasons)}")

                invoices.append(invoice)

            except Exception as e:
                print(f"  ERR 处理失败: {e}")

        if not invoices:
            print("没有成功识别任何发票")
            return None

        print("\n执行智能选择...")
        final_result = self.selector.select(invoices)
        final_result.month = self.month

        self.file_manager.ensure_directories()

        print("\n处理文件...")
        for inv in invoices:
            try:
                self.file_manager.process_file(inv)
            except Exception as e:
                print(f"  警告: 文件处理失败 - {inv.original_name}: {e}")

        print("\n生成报告...")
        self.reporter.generate(final_result, self.output_dir)
        self.reporter.print_summary(final_result)

        return final_result

    def _scan_invoice_pool(self) -> list[Path]:
        """扫描发票池，仅读取 invoice/*.pdf。"""
        if not self.invoice_pool.exists():
            print(f"警告: 发票池目录不存在 - {self.invoice_pool}")
            return []

        files = list(self.invoice_pool.glob("*.pdf"))
        return sorted(files, key=lambda x: x.name.lower())