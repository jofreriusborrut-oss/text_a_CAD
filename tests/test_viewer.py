import re

from textacad.viewer import viewer_html


def test_viewer_embeds_stl_and_three_js():
    html = viewer_html(b"solid test\nendsolid test\n", height=300)
    assert "c29saWQgdGVzdA" in html                 # base64 of "solid test"
    assert "OrbitControls" in html and "STLLoader" in html
    assert "cdn." not in html                        # works offline
    # The library text must not close the <script> tag by accident.
    assert len(re.findall(r"</script>", html)) == html.count("<script")
