from __future__ import annotations


Point = list[float]
Polygon = list[Point]


def signed_area(polygon: Polygon) -> float:
    return sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    ) / 2


def polygon_area(polygon: Polygon) -> float:
    return abs(signed_area(polygon))


def _inside(point: Point, edge_start: Point, edge_end: Point, orientation: float) -> bool:
    cross = (edge_end[0] - edge_start[0]) * (point[1] - edge_start[1]) - (
        edge_end[1] - edge_start[1]
    ) * (point[0] - edge_start[0])
    return cross * orientation >= -1e-9


def _intersection(start: Point, end: Point, edge_start: Point, edge_end: Point) -> Point:
    x1, y1 = start
    x2, y2 = end
    x3, y3 = edge_start
    x4, y4 = edge_end
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-12:
        return [end[0], end[1]]
    determinant1 = x1 * y2 - y1 * x2
    determinant2 = x3 * y4 - y3 * x4
    return [
        (determinant1 * (x3 - x4) - (x1 - x2) * determinant2) / denominator,
        (determinant1 * (y3 - y4) - (y1 - y2) * determinant2) / denominator,
    ]


def convex_intersection(subject: Polygon, clip: Polygon) -> Polygon:
    output = [list(point) for point in subject]
    if len(output) < 3 or len(clip) < 3:
        return []
    orientation = 1.0 if signed_area(clip) >= 0 else -1.0
    for index, edge_end in enumerate(clip):
        edge_start = clip[index - 1]
        input_polygon = output
        output = []
        if not input_polygon:
            break
        start = input_polygon[-1]
        for end in input_polygon:
            end_inside = _inside(end, edge_start, edge_end, orientation)
            start_inside = _inside(start, edge_start, edge_end, orientation)
            if end_inside:
                if not start_inside:
                    output.append(_intersection(start, end, edge_start, edge_end))
                output.append(end)
            elif start_inside:
                output.append(_intersection(start, end, edge_start, edge_end))
            start = end
    return output


def polygon_iou(first: Polygon, second: Polygon) -> float:
    first_area = polygon_area(first)
    second_area = polygon_area(second)
    if first_area <= 0 or second_area <= 0:
        return 0.0
    intersection = polygon_area(convex_intersection(first, second))
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def maximum_bipartite_matches(edges: list[list[int]], right_size: int) -> list[tuple[int, int]]:
    right_match = [-1] * right_size

    def augment(left: int, seen: set[int]) -> bool:
        for right in edges[left]:
            if right in seen:
                continue
            seen.add(right)
            if right_match[right] == -1 or augment(right_match[right], seen):
                right_match[right] = left
                return True
        return False

    for left in range(len(edges)):
        augment(left, set())
    return [(left, right) for right, left in enumerate(right_match) if left != -1]


def match_polygons(
    predicted: list[Polygon], ground_truth: list[Polygon], threshold: float
) -> list[tuple[int, int, float]]:
    scored_edges: list[list[tuple[int, float]]] = []
    for pred in predicted:
        candidates = [
            (gt_index, polygon_iou(pred, gt)) for gt_index, gt in enumerate(ground_truth)
        ]
        candidates = [item for item in candidates if item[1] >= threshold]
        candidates.sort(key=lambda item: item[1], reverse=True)
        scored_edges.append(candidates)
    matches = maximum_bipartite_matches(
        [[index for index, _ in candidates] for candidates in scored_edges], len(ground_truth)
    )
    return [
        (left, right, next(score for index, score in scored_edges[left] if index == right))
        for left, right in matches
    ]

