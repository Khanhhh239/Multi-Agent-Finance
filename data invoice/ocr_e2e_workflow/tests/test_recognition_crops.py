import unittest
from PIL import Image, ImageDraw
from src.adapters.recognition_crops import rectified_crop, line_segments


class RecognitionCropTests(unittest.TestCase):
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
