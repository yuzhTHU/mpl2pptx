from lxml import etree as ET
import pytest

from mpl2pptx.svg.document import figure_viewport


@pytest.mark.parametrize(("attrs", "size"), [
    ('width="522.15748pt" height="310.07874pt"', (522.15748, 310.07874)),
    ('width="8cm" height="120mm" viewBox="-5 10 8 12"', (8 * 72 / 2.54, 12 * 72 / 2.54)),
    ('width="192" height="96px"', (144, 72)),
    ('width="2in" height="12pc"', (144, 144)),
    ('viewBox="20 30 192 96"', (144, 72)),
    ('width="180pt" viewBox="0 0 2 1"', (180, 90)),
    ('height="100pt" viewBox="0 0 2 1"', (200, 100)),
])
def test_physical_dimensions(attrs, size):
    width, height, _ = figure_viewport(ET.fromstring(f"<svg {attrs}/>"))
    assert (width, height) == pytest.approx(size)


def test_letterbox_and_nonzero_origin():
    svg = ET.fromstring('<svg width="180pt" height="90pt" viewBox="10 20 100 100"/>')
    _, _, transform = figure_viewport(svg)
    assert transform.transformPoint((10, 20)) == pytest.approx((45, 0))
    assert transform.transformPoint((110, 120)) == pytest.approx((135, 90))


@pytest.mark.parametrize("attrs", ['width="80%" height="72pt"', 'viewBox="0 0 -10 10"', 'width="0" height="96px"'])
def test_unresolvable_sizes(attrs):
    with pytest.raises(ValueError):
        figure_viewport(ET.fromstring(f"<svg {attrs}/>"))
