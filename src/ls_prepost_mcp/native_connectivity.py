"""Native keyword beam-connectivity readback avoids a reproduced array-binding heap fault."""
from pathlib import Path

from .config import scl_command_path


def beam_connectivity_prelude(directory: Path) -> str:
    return (
        "import os,json,DataCenter as dc,LsPrePost as lp\n"
        "os.chdir("+repr(str(directory))+")\n"
        'count=int(dc.get_data("num_beam_elements"))\n'
        'assert 0<=count<=1000000,"Beam inspection resource budget exceeded"\n'
        'try:\n    mass_count=int(dc.get_data("num_mass_elements"))\n'
        'except RuntimeError:\n    mass_count=None\n'
        'assert mass_count is None or 0<=mass_count<=1000000,"Mass inspection resource budget exceeded"\n'
        'if count or mass_count:\n'
        '    try:\n'
        '        source=dict(model_directory=str(dc.get_data("model_directory")), counts=dict(nodes=int(dc.get_data("num_nodes")), elements=int(dc.get_data("num_elements")), states=int(dc.get_data("num_states"))))\n'
        '    except Exception:\n        source=None\n'
        '    with open("beam-export-before.json","w") as stream: json.dump(source,stream)\n'
        'if count or mass_count:\n    lp.execute_command(' + repr('save keyword ' + scl_command_path(directory/'beam-connectivity.k')) + ')\n'
        'with open("beam-count.json","w") as stream: json.dump(count,stream)\n'
        'with open("mass-count.json","w") as stream: json.dump(mass_count,stream)\n'
    )
