import asyncio

import pytest

from ls_prepost_mcp.config import Settings
from ls_prepost_mcp.keyword_documentation import KeywordField
from ls_prepost_mcp.knowledge import command_help, keyword_fields, search_docs
from ls_prepost_mcp.knowledge_index import Document, build_index
from ls_prepost_mcp.server import build_server


def test_document_tools_require_explicit_index_and_keep_private_opt_in(tmp_path,monkeypatch):
    monkeypatch.delenv("LSPP_KNOWLEDGE_INDEX",raising=False)
    with pytest.raises(ValueError,match="LSPP_KNOWLEDGE_INDEX"):
        search_docs("nodes")
    path=tmp_path/"index.sqlite"
    docs=[Document("catalog","command","genselect target node","Set selection mode to nodal","repo://commands","MIT","public","catalog"),
          Document("manual","api","get_data","Read num_nodes","local://api","copyright","private","2024")]
    build_index(path,docs)
    monkeypatch.setenv("LSPP_KNOWLEDGE_INDEX",str(path))
    row=command_help("genselect target node")[0]
    assert row["evidence_level"]=="source_example" and row["version"]=="catalog"
    assert search_docs("get_data",category="api")==[]
    assert search_docs("get_data",category="api",include_private=True)[0]["evidence_level"]=="documented"
    assert search_docs("如何选择节点",category="command")[0]["query_expansion"]==["genselect","target","node"]


def test_keyword_prefix_alias_and_verification_scope_are_preserved(tmp_path,monkeypatch):
    field=KeywordField("*CONTACT_ERODING_SURFACE_TO_SURFACE",None,2,"sfsa",0,10,"Penalty stiffness",[],None,
                       dict(evidence="verified",attribution="provider",detail="Card solver acceptance"),"MIT","0.12.1",["sfs"])
    path=tmp_path/"index.sqlite"
    build_index(path,[],[field])
    monkeypatch.setenv("LSPP_KNOWLEDGE_INDEX",str(path))
    rows=keyword_fields("CONTACT_ERODING","SFS")
    assert len(rows)==1 and rows[0]["keyword_field"]["field"]=="sfsa"
    assert rows[0]["evidence_level"]=="native_verified" and "not verification of every field" in rows[0]["evidence_scope"]
    assert rows[0]["verification_attribution"]=="provider"
    assert "line_start" not in rows[0]


def test_new_knowledge_tools_are_registered_without_native_side_effects(tmp_path):
    server=build_server(Settings(tmp_path))
    names={tool.name for tool in asyncio.run(server.list_tools())}
    assert {"search_docs","keyword_fields","command_help"}<=names
    assert not list(tmp_path.iterdir())
