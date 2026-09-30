"""Runs inside LS-PrePost, not in the external MCP Python environment."""
import json

import DataCenter as dc

with open("nodes.json", "w") as output:
    json.dump({"nodes": int(dc.get_data("num_nodes"))}, output)
