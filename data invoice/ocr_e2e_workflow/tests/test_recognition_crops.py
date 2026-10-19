import unittest
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from src.adapters.recognition_crops import rectified_crop, line_segments


class RecognitionCropTests(unittest.TestCase):
    def test_recognition_only_splits_without_detector_and_keeps_segment_spans(self):
        from src.adapters.vietocr_adapter import PPOCRV6VietOCRAdapter
        class Recognizer:
            def predict(self,image):return 'observed'
        adapter=object.__new__(PPOCRV6VietOCRAdapter)
        adapter.recognition_only=True;adapter.recognizer=Recognizer()
        adapter.config={'recognizer':{'split_long_lines':True,'max_line_aspect':10,'max_line_parts':3}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'line.png'
            with Image.new('RGB',(400,10),'white') as image:image.save(path)
            result=adapter.infer(path)
        self.assertEqual(result['document_text_raw'],'observed observed observed')
        spans=result['metadata']['x_spans']
        self.assertEqual(len(spans),3);self.assertEqual(spans[0][0],0);self.assertEqual(spans[-1][1],400)
        self.assertNotIn('confidence',result)

    def test_recognition_only_failure_propagates_instead_of_empty_success(self):
        from src.adapters.vietocr_adapter import PPOCRV6VietOCRAdapter
        class Recognizer:
            def predict(self,image):raise RuntimeError('model failed')
        adapter=object.__new__(PPOCRV6VietOCRAdapter)
        adapter.recognition_only=True;adapter.recognizer=Recognizer();adapter.config={}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'line.png'
            with Image.new('RGB',(100,10),'white') as image:image.save(path)
            with self.assertRaises(RuntimeError):adapter.infer(path)

    def test_rectification_preserves_order_and_colors(self):
        with Image.new('RGB', (100, 60), 'white') as image:
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 40, 40), fill='red')
            draw.rectangle((41, 10, 70, 40), fill='blue')
            crop = rectified_crop(image, [(70, 40), (10, 40), (10, 10), (70, 10)])
            self.assertGreater(crop.getpixel((5, 10))[0], 200)
            self.assertGreater(crop.getpixel((50, 10))[2], 200)
            crop.close()

    def test_no_split_through_solid_ink_and_bounded_parts(self):
        with Image.new('RGB', (400, 10), 'black') as image:
            parts = line_segments(image, max_aspect=10, max_parts=3)
            self.assertEqual([span for _, span in parts], [(0, 400)])
            for part, _ in parts:
                part.close()
        with Image.new('RGB', (400, 10), 'white') as image:
            parts = line_segments(image, max_aspect=10, max_parts=3)
            self.assertEqual(len(parts), 3)
            self.assertEqual(parts[0][1][0], 0)
            self.assertEqual(parts[-1][1][1], 400)
            self.assertTrue(all(a[1][1] == b[1][0] for a, b in zip(parts, parts[1:])))
            for part, _ in parts:
                part.close()

    def test_rejects_invalid_geometry_and_budgets(self):
        with Image.new('RGB', (40, 20), 'white') as image:
            with self.assertRaises(ValueError):
                rectified_crop(image, [(1, 1)] * 4)
            with self.assertRaises(ValueError):
                line_segments(image, max_parts=20)


if __name__ == '__main__':
    unittest.main()
