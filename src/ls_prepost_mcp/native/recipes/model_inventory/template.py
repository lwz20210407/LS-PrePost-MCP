import json

import DataCenter as dc

counts={"nodes":int(dc.get_data("num_nodes")),"elements":int(dc.get_data("num_elements")),"states":int(dc.get_data("num_states")),"parts":int(dc.get_data("num_validparts"))}
with open("inventory.json","w") as stream:
    json.dump(counts,stream)
