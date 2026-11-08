"""Bounded crop transforms for recognizer experiments; no field/value guessing."""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageOps


def rectified_crop(image, polygon, padding=0):
    points = np.asarray(polygon, dtype=float)
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise ValueError('rectification requires four finite points')
    center = points.mean(axis=0)
    points = points[np.argsort(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))]
    points = np.roll(points, -int(np.argmin(points.sum(axis=1))), axis=0)
    tl, tr, br, bl = points
    width = int(math.ceil(max(np.linalg.norm(tr-tl), np.linalg.norm(br-bl))))
    height = int(math.ceil(max(np.linalg.norm(bl-tl), np.linalg.norm(br-tr))))
    if min(width, height) < 2 or width * height > image.width * image.height * 2:
        raise ValueError('degenerate or oversized crop')
    crop = image.transform((width, height), Image.Transform.QUAD,
                           tuple(np.concatenate((tl, bl, br, tr))),
                           resample=Image.Resampling.BICUBIC, fillcolor='white')
    if padding:
        if not 0 <= padding <= 16:
            crop.close()
            raise ValueError('padding must be 0..16 pixels')
        padded = ImageOps.expand(crop, border=padding, fill='white')
        crop.close()
        crop = padded
    return crop


def line_segments(image, max_aspect=14.0, max_parts=4):
    """Split only at clear background columns; return owned crops and x spans.

    No whitespace valley means abstain from splitting. Numeric tokens cannot be
    split through ink; complex backgrounds may therefore remain a single crop.
    """
    if not 2 <= max_aspect <= 40 or not 1 <= max_parts <= 8:
        raise ValueError('invalid crop segmentation budget')
    limit = max(1, int(image.height * max_aspect))
    if image.width <= limit:
        return [(image.copy(), (0, image.width))]
    pixels = np.asarray(image.convert('L'))
    ink = (pixels < 190).sum(axis=0)
    spans = []
    left = 0
    while image.width - left > limit and len(spans) < max_parts - 1:
        low = left + int(limit * .55)
        high = min(left + limit, image.width - int(image.height * 2))
        gaps = [x for x in range(low, high) if ink[x] == 0 and ink[max(0, x-1)] == 0]
        if not gaps:
            break
        cut = max(gaps)
        spans.append((left, cut))
        left = cut
    spans.append((left, image.width))
    return [(image.crop((left, 0, right, image.height)), (left, right)) for left, right in spans]
