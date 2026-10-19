"""Small, deterministic geometry helpers. This is not a font or draw.io renderer."""

from dataclasses import dataclass
import math
import unicodedata


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return (self.x + self.width / 2, self.y + self.height / 2)


def absolute_rect(identifier, rects, parents):
    """Resolve parent-relative rectangles; header height is already in child y."""
    rect = rects[identifier]
    x, y = rect.x, rect.y
    seen = {identifier}
    parent = parents.get(identifier)
    while parent is not None:
        if parent in seen:
            raise ValueError("parent cycle")
        seen.add(parent)
        owner = rects[parent]
        x += owner.x
        y += owner.y
        parent = parents.get(parent)
    return Rect(x, y, rect.width, rect.height)


def estimate_text_width(text, font_size=18):
    """Conservative heuristic: wide glyphs 1 em, other glyphs 0.58 em.

    This cannot establish whether installed fonts render text without overflow.
    Combining marks do not add width; tabs are four spaces.
    """
    widths = []
    for line in str(text).split("\n"):
        units = 0.0
        for char in line:
            if unicodedata.combining(char):
                continue
            if char == "\t":
                units += 2.32
            else:
                units += 1.0 if unicodedata.east_asian_width(char) in "WFA" else 0.58
        widths.append(units * font_size)
    return max(widths, default=0)


def wrap_text(text, width, font_size=18):
    """Prefer whitespace breaks; hard-wrap only unspaced or overlong text.

    Explicit newlines are preserved. This is an approximate width operation,
    not language-aware typography or a substitute for rendered-text review.
    """
    if width <= 0:
        raise ValueError("text width must be positive")
    result = []
    for raw in str(text).split("\n"):
        line = ""
        for char in raw:
            if line and estimate_text_width(line + char, font_size) > width:
                candidate = line + char
                breaks = [index for index, value in enumerate(candidate) if value.isspace() and candidate[:index].strip()]
                if breaks:
                    split = breaks[-1]
                    result.append(candidate[:split].rstrip())
                    line = candidate[split + 1:].lstrip()
                else:
                    result.append(line.rstrip())
                    line = char.lstrip()
            else:
                line += char
        result.append(line.rstrip())
    return "\n".join(result)


def simplify_points(points):
    result = []
    for point in points:
        point = tuple(point)
        if result and point == result[-1]:
            continue
        result.append(point)
        while len(result) >= 3:
            a, b, c = result[-3:]
            if ((a[0] == b[0] == c[0] and min(a[1], c[1]) <= b[1] <= max(a[1], c[1]))
                    or (a[1] == b[1] == c[1] and min(a[0], c[0]) <= b[0] <= max(a[0], c[0]))):
                result.pop(-2)
            else:
                break
    return result


def polyline_segments(points):
    return list(zip(points, points[1:]))


def proper_intersections(first, second):
    """Count strict perpendicular crossings, excluding shared endpoints."""
    count = 0
    for a, b in polyline_segments(first):
        for c, d in polyline_segments(second):
            if a[1] == b[1] and c[0] == d[0]:
                if min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1]):
                    count += 1
            elif a[0] == b[0] and c[1] == d[1]:
                if min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1]):
                    count += 1
    return count


def segment_hits_rect(a, b, rect):
    """Interior collision only; touching a rectangle boundary is not an overlap."""
    if a[0] == b[0]:
        return rect.x < a[0] < rect.right and max(min(a[1], b[1]), rect.y) < min(max(a[1], b[1]), rect.bottom)
    if a[1] == b[1]:
        return rect.y < a[1] < rect.bottom and max(min(a[0], b[0]), rect.x) < min(max(a[0], b[0]), rect.right)
    raise ValueError("non-orthogonal segment")


def polyline_length(points):
    return sum(math.dist(a, b) for a, b in polyline_segments(points))


def midpoint(points):
    remaining = polyline_length(points) / 2
    for a, b in polyline_segments(points):
        length = math.dist(a, b)
        if length and remaining <= length:
            ratio = remaining / length
            return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)
        remaining -= length
    return points[0]
