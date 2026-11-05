"""General inflection retrieval oracles, authored independently of the LS-PrePost QA sets."""
import pytest

from ls_prepost_mcp.knowledge_index import Document, build_index, search_index


@pytest.mark.parametrize("base,variant",[
    ("property","properties"),("directory","directories"),("class","classes"),
    ("record","records"),("record","recorded"),("record","recording"),
    ("update","updated"),("update","updating"),("review","reviewed"),("review","reviewing"),
])
def test_regular_word_family_retrieval_in_both_directions(tmp_path,base,variant):
    for number,(query,word) in enumerate([(base,variant),(variant,base)]):
        path=tmp_path/f"family-{number}.sqlite"
        build_index(path,[Document("oracle","command","Generic reference",word,"test://oracle","MIT","public")])
        results=search_index(path,query)
        assert [row["source_id"] for row in results]==["oracle"],(query,word)


@pytest.mark.parametrize("query,identifier",[
    ("entry7","entry70"),("string","str_flag"),("speed","spe_value"),("spring","spr_id"),
])
def test_word_expansion_does_not_turn_fragments_into_identifier_matches(tmp_path,query,identifier):
    path=tmp_path/"literal.sqlite"
    build_index(path,[Document("identifier","command","Generic reference",identifier,"test://identifier","MIT","public")])
    assert search_index(path,query)==[]
