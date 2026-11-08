from src.adapters.paddleocr_vl_adapter import paddle_vl_blocks_to_detections
from src.adapters.paddle_common import paddle_result_to_detections
from src.adapters.surya_adapter import surya_result_to_output


def test_surya_blocks_are_normalized_without_claiming_line_level_geometry():
    payload = {
        "receipt": [
            {
                "blocks": [
                    {
                        "html": "<b>Tổng tiền</b>: 35.000đ",
                        "polygon": [[1, 2], [11, 2], [11, 8], [1, 8]],
                        "confidence": 0.9,
                        "label": "Text",
                        "reading_order": 0,
                    }
                ]
            }
        ]
    }

    text, blocks, detections = surya_result_to_output(payload)

    assert text == "Tổng tiền : 35.000đ"
    assert blocks[0]["label"] == "Text"
    assert detections[0]["polygon"][2] == [11.0, 8.0]


def test_paddle_vl_bbox_is_converted_to_polygon():
    values = [
        {
            "res": {
                "parsing_res_list": [
                    {
                        "block_bbox": [10, 20, 50, 60],
                        "block_content": "Hóa đơn",
                        "block_label": "text",
                        "block_id": 7,
                    }
                ]
            }
        }
    ]

    detections = paddle_vl_blocks_to_detections(values)

    assert detections[0]["polygon"] == [[10.0, 20.0], [50.0, 20.0], [50.0, 60.0], [10.0, 60.0]]
    assert detections[0]["text_raw"] == "Hóa đơn"


def test_paddle_polygon_is_mapped_back_after_orientation_rotation():
    values = [
        {
            "res": {
                "doc_preprocessor_res": {"angle": 270},
                "rec_polys": [[[10, 20], [30, 20], [30, 40], [10, 40]]],
                "rec_texts": ["Hóa đơn"],
                "rec_scores": [0.9],
            }
        }
    ]

    detections = paddle_result_to_detections(values, source_size=(100, 50))

    assert detections[0]["polygon"] == [
        [20.0, 40.0],
        [20.0, 20.0],
        [40.0, 20.0],
        [40.0, 40.0],
    ]
