"""Native keyword beam-connectivity readback avoids a reproduced array-binding heap fault."""
from pathlib import Path


def beam_connectivity_prelude(directory: Path) -> str:
    return (
        "import os,json,DataCenter as dc,LsPrePost as lp\n"
        "os.chdir("+repr(str(directory))+")\n"
        'count=int(dc.get_data("num_beam_elements"))\n'
        'assert 0<=count<=1000000,"Beam inspection resource budget exceeded"\n'
        'if count:\n    lp.execute_command(\'save keyword "beam-connectivity.k"\')\n'
        'with open("beam-count.json","w") as stream: json.dump(count,stream)\n'
    )
