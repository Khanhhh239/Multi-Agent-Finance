"""Independent fictional name pairs; similarity truth is separate from fraud."""
import random
from .noise_policy import name_similarity


def run_challenge(threshold=.85):
    rng = random.Random(20261014)
    brands = ['Sao Bắc', 'An Phú', 'Bình Minh', 'Hải Đăng', 'Minh Long', 'Trường Sơn',
        'Thiên Hà', 'Việt Hưng', 'Hòa Bình', 'Đông Dương', 'Thanh Trúc', 'Hoàng Gia',
        'Nam Việt', 'Kim Sơn', 'Đại Phát', 'Bảo Ngọc', 'Tân Tiến', 'Phúc Lộc',
        'Hương Giang', 'Hồng Hà', 'Đại Dương', 'Ngọc Lan', 'Vạn Xuân', 'Thái An']
    rows = []
    for i in range(180):
        brand, other = rng.sample(brands, 2)
        sector = rng.choice(['Cơ khí', 'Gốm sứ', 'Dệt may', 'Vận tải', 'Phần mềm', 'Bao bì'])
        # All expected relationships are assigned before invoking the matcher.
        for kind, left, right, near, same in [
            ('intentional_alias', f'Công ty TNHH {sector} {brand}', f'{sector} {brand.upper()} Co., Ltd', True, True),
            ('legitimate_similar_affiliates', f'Công ty TNHH {sector} {brand} Miền Bắc', f'Công ty CP {sector} {brand} Miền Nam', True, False),
            ('independent_names_same_legal_form', f'Công ty TNHH {sector} {brand}', f'Công ty TNHH {sector} {other}', False, False),
        ]:
            rows.append(dict(pair_id=f'PAIR_{i:03}_{kind}', kind=kind, left=left, right=right,
                expected_name_candidate=near, same_entity=same, fraud_truth_available=False,
                left_tax_id=f'MST_FAKE_{i}_A', right_tax_id=f'MST_FAKE_{i}_A' if same else f'MST_FAKE_{i}_B',
                relationship_disclosed=kind == 'legitimate_similar_affiliates'))
    for row in rows:
        similarity = name_similarity(row['left'], row['right'])
        row.update(similarity=similarity, candidate=similarity is not None and similarity > threshold,
                   operational_points=0, hard_trigger=False)
    return rows
