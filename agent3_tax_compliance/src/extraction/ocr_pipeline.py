import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class OCRPipeline:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._reader = None

    @property
    def reader(self):
        if self._reader is None:
            import easyocr
            # We must store models in D drive as C drive has limited space
            model_dir = "d:/financial/agent3_tax_compliance/data/models/easyocr"
            os.makedirs(model_dir, exist_ok=True)
            logger.info(f"Initializing EasyOCR reader with models stored in: {model_dir}")
            self._reader = easyocr.Reader(['vi', 'en'], model_storage_directory=model_dir)
        return self._reader

    def extract_text(self, image_path: str) -> str:
        """
        Extracts text from an invoice image.
        If OCR is disabled, returns mock transaction descriptions based on the filename
        to facilitate end-to-end testing and demonstration.
        """
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            return ""

        filename = os.path.basename(image_path).lower()
        logger.info(f"Processing image {filename} via OCR Pipeline...")

        if not self.enabled:
            logger.info("Local OCR is disabled. Running in DEMO mock mode.")
            # Provide high-quality mock data for testing based on filename keywords
            if "cash_20m" in filename:
                return "Hóa đơn số 01234, ngày 2026-07-19, mua linh kiện máy tính, trị giá 25.000.000 VND, thanh toán bằng tiền mặt (TM), MST nhà cung cấp: 0102030405."
            elif "welfare" in filename:
                return "Chi tiền hỗ trợ sinh nhật nhân viên công ty Nguyễn Văn A, số tiền 1.500.000 VND từ quỹ phúc lợi, ngày 2026-07-19."
            elif "car_1.6b" in filename:
                return "Khấu hao xe ô tô chở người 5 chỗ Toyota Camry, biển số 30F-12345, nguyên giá 1.800.000.000 VND, ngày trích khấu hao 2026-07-19."
            elif "vendor_risk" in filename:
                return "Hóa đơn dịch vụ ăn uống tiếp khách ngày 2026-07-19, trị giá 5.000.000 VND, MST người bán 0100100100 (nhà cung cấp rủi ro cao)."
            else:
                return "Giao dịch chi phí văn phòng phẩm ngày 2026-07-19, trị giá 500.000 VND, chuyển khoản, đầy đủ hóa đơn chứng từ."

        try:
            logger.info(f"Running EasyOCR on: {image_path}")
            result = self.reader.readtext(image_path)
            text_lines = [line[1] for line in result]
            extracted_text = " ".join(text_lines)
            logger.info(f"Successfully extracted OCR text: {extracted_text}")
            return extracted_text
        except Exception as e:
            logger.error(f"Error during EasyOCR extraction: {e}")
            return ""
