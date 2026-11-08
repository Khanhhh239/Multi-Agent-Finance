import importlib.util
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from src.config import Settings
from src.adapters.ocr.registry import load_default_config,EngineRegistry
from src.adapters.ocr.protocol import OCRError

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('coverage_geometry',ROOT/'data invoice/ocr_e2e_workflow/src/adapters/coverage_geometry.py')
geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)


def detection(x0,y0,x1,y1):return {'polygon':[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],'text_raw':'','source_id':'base','confidence':.8}


class CoverageTests(unittest.TestCase):
    def test_rotation_maps_landmarks_back_to_exact_source(self):
        with Image.new('RGB',(300,200),'white') as image:
            for angle in (-3,-.5,0,.5,3):
                rotated,forward,back=geometry.rotation(image,angle)
                self.addCleanup(rotated.close)
                for p in ((0,0),(300,200),(130,70),(0,200)):
                    actual=geometry.point(back,geometry.point(forward,p))
                    self.assertAlmostEqual(actual[0],p[0]);self.assertAlmostEqual(actual[1],p[1])

    def test_blank_page_does_not_invent_skew(self):
        with Image.new('RGB',(300,200),'white') as image:
            angle,gain=geometry.estimate_skew(image);self.assertEqual(angle,0)
            processed,back,meta=geometry.prepare(image,True);self.addCleanup(processed.close)
            self.assertEqual(back,geometry.IDENTITY);self.assertEqual(meta['angle'],0)

    def test_known_skew_is_recovered_with_strong_projection_gain(self):
        with Image.new('RGB',(600,600),'white') as image:
            draw=ImageDraw.Draw(image)
            for y in range(80,520,30):draw.line((70,y,530,y),fill='black',width=3)
            tilted,_,_=geometry.rotation(image,2);self.addCleanup(tilted.close)
            angle,gain=geometry.estimate_skew(tilted)
            self.assertAlmostEqual(angle,-2,delta=.5);self.assertGreater(gain,1.2)

    def test_pixel_angle_and_tile_budgets(self):
        with Image.new('RGB',(300,200)) as image:
            for angle in (4,float('nan')):
                with self.assertRaises(ValueError):geometry.rotation(image,angle)
            with self.assertRaises(ValueError):geometry.rotation(image,2,max_pixels=100)
        self.assertEqual(len(geometry.tile_boxes(1000,1000)),4)
        self.assertEqual(geometry.tile_boxes(20,20),[])
        with self.assertRaises(ValueError):geometry.tile_boxes(100,100,.8)

    def test_tiles_add_only_uncovered_boxes_and_reject_cut_words(self):
        baseline=[detection(10,10,80,30)]
        tiles=[((0,0,560,560),[detection(10,10,80,30),detection(200,200,270,220),detection(500,50,559,70)]),
               ((440,0,1000,560),[detection(0,20,80,40)])]
        result,meta=geometry.add_tiles(baseline,tiles,(1000,1000))
        self.assertEqual(len(result),2);self.assertEqual(meta['added_boxes'],1)
        self.assertEqual(meta['edge_boxes_rejected'],2);self.assertEqual(result[0],baseline[0])
        self.assertEqual(result[1]['polygon'],detection(200,200,270,220)['polygon'])

    def test_tile_offsets_preserve_original_coordinates_and_bound_count(self):
        result,_=geometry.add_tiles([], [((440,440,1000,1000),[detection(20,20,80,40),detection(100,100,160,130)])],(1000,1000),max_extra=1)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['polygon'][0],[460,460])
        self.assertEqual(geometry.map_polygon([[-1,0],[100,120],[20,30]],geometry.IDENTITY,(100,100)),[[0.,0.],[100,100],[20,30]])

    def test_local_profile_and_render_settings_are_validated(self):
        with patch.dict(os.environ,{'CAPTURE_RENDER_DPI':'200','AGENT3_OCR_PROFILE':'ppocrv6_vietocr_tiles'}):
            self.assertEqual(Settings.from_env().render_dpi,200)
            self.assertEqual(load_default_config().model_id,'ppocrv6_vietocr_tiles')
        for bad in ('../secrets','C:/secret','a.json'):
            with patch.dict(os.environ,{'AGENT3_OCR_PROFILE':bad}):
                with self.assertRaises(OCRError):load_default_config()
        p=EngineRegistry().get('ppocrv6_vietocr_coverage')
        self.assertIn('src/adapters/coverage_geometry.py',p.source_files)


if __name__=='__main__':unittest.main()
