"""Generated scripts may only build geometry."""
import pytest

from textacad.prompts import EXAMPLES
from textacad.safety import find_problems

GOOD = "import math\nimport cadquery as cq\nPARAMS = {}\nresult = cq.Workplane('XY').box(1, 2, math.pi)\n"


def test_normal_scripts_pass():
    assert find_problems(GOOD) == []
    for _, code in EXAMPLES:
        assert find_problems(code) == []


@pytest.mark.parametrize("bad", [
    "import os\nresult = 1\n",
    "import cadquery as cq\nfrom pathlib import Path\nresult = 1\n",
    "import cadquery as cq\nopen('secret.txt').read()\nresult = 1\n",
    "import cadquery as cq\nresult = eval('1+1')\n",
    "import cadquery as cq\nx = ().__class__.__bases__\nresult = 1\n",
    "import cadquery as cq\nresult = __import__('os').getcwd()\n",
    "import cadquery as cq\nimport subprocess\nsubprocess.run(['calc'])\nresult = 1\n",
    "import cadquery as cq\nwith cq.Workplane('XY') as w:\n    pass\nresult = 1\n",
])
def test_dangerous_scripts_are_reported(bad):
    problems = find_problems(bad)
    assert problems and all(p.startswith("line ") for p in problems)


def test_syntax_errors_are_raised():
    with pytest.raises(SyntaxError):
        find_problems("result = (1,\n")
