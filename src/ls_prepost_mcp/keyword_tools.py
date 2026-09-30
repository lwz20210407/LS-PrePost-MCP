"""Version-aligned structured keyword operations; no arbitrary Python or raw cards."""
import inspect
import math
import re
from functools import lru_cache
from importlib.metadata import version

from .deck_backend import api
from .jobs import check_artifact
from .model_deck import load_standalone


@lru_cache(maxsize=1)
def keyword_types():
    _, kw = api()
    from ansys.dyna.core.lib.keyword_base import KeywordBase
    return {name: getattr(kw,name) for name in dir(kw)
            if not name.startswith('_') and inspect.isclass(getattr(kw,name))
            and issubclass(getattr(kw,name),KeywordBase) and getattr(kw,name) is not KeywordBase}


def keyword_type(name):
    if name not in keyword_types():
        raise ValueError('Unknown keyword class; use list_pydyna_keywords')
    return keyword_types()[name]


def new_keyword(cls):
    card = cls()
    # 0.12 SECTION card sets have no first row after an empty constructor.
    # Initialize the public card-set interface before scalar property access.
    if callable(getattr(card,'add_set',None)) and hasattr(card,'sets') and len(card.sets)==0:
        card.add_set()
    return card


def properties(cls):
    from ansys.dyna.core.lib.keyword_base import KeywordBase
    result = {}
    for base in cls.__mro__:
        if base is KeywordBase:
            break
        for name, prop in vars(base).items():
            if isinstance(prop,property) and prop.fset and not name.startswith('_'):
                result.setdefault(name,prop)
    return result


def scalar(value):
    if value is None or type(value) in (bool,int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value,str) and len(value)<=1000 and not any(ord(c)<32 for c in value):
        return value
    raise ValueError('Field requires a finite scalar or a single-line string (max 1000 characters)')


def snapshot(card, name):
    import numpy as np
    import pandas as pd
    from ansys.dyna.core.lib.series_card import SeriesCard
    value = getattr(card,name)
    if isinstance(value,pd.DataFrame):
        return value.copy()
    if isinstance(value,np.ndarray):
        return value.tolist()
    if isinstance(value,SeriesCard):
        return list(value)
    if hasattr(value,'tolist'):
        return value.tolist()
    return value


def assign(card, values):
    import numpy as np
    import pandas as pd
    from ansys.dyna.core.lib.series_card import SeriesCard
    available = properties(type(card))
    if not isinstance(values,dict) or not values:
        raise ValueError('Nonempty fields mapping required')
    unknown = set(values)-set(available)
    if unknown:
        raise ValueError('Unknown or non-data fields: '+', '.join(sorted(unknown)))
    for key,value in values.items():
        if key not in available:
            raise ValueError('Unknown or non-data field: '+str(key))
        current = getattr(card,key)
        if isinstance(current,pd.DataFrame):
            if not isinstance(value,list) or not value or len(value)>100000:
                raise ValueError('Table field requires 1..100000 row objects')
            if any(not isinstance(row,dict) or not row or not set(row)<=set(current.columns) for row in value):
                raise ValueError('Unknown/empty table columns in '+key)
            rows = [{k:scalar(v) for k,v in row.items()} for row in value]
            setattr(card,key,pd.DataFrame(rows))
        elif isinstance(current,(list,np.ndarray,SeriesCard)):
            if not isinstance(value,list) or len(value)>100000:
                raise ValueError('Series requires a bounded list')
            setattr(card,key,[scalar(v) for v in value])
        else:
            setattr(card,key,scalar(value))


def equal(a,b):
    import numpy as np
    import pandas as pd
    if isinstance(a,pd.DataFrame):
        if not isinstance(b,pd.DataFrame) or not set(a.columns)<=set(b.columns) or len(a)!=len(b):
            return False
        return all(equal(x,y) for x,y in zip(a.to_numpy().flat,b[list(a.columns)].to_numpy().flat))
    if isinstance(a,(list,tuple,np.ndarray)):
        return isinstance(b,(list,tuple,np.ndarray)) and len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if a is None or isinstance(a,float) and math.isnan(a):
        return b is None or pd.isna(b)
    if isinstance(a,(int,np.integer)) and not isinstance(a,bool):
        return isinstance(b,(int,float,np.number)) and a == b
    if isinstance(a,(float,np.number)) and not isinstance(a,bool):
        try:
            return math.isclose(float(a),float(b),rel_tol=2e-6,abs_tol=1e-12)
        except (TypeError,ValueError):
            return False
    return a==b


def export_verified(deck, output, expected):
    Deck,_ = api()
    validation = deck.validate()
    if validation.has_errors():
        raise ValueError('PyDYNA validation: '+str(validation.get_summary()))
    deck.export_file(str(output),validate=True)
    reloaded = Deck()
    reloaded.import_file(str(output))
    if len(reloaded.keywords)!=len(deck.keywords):
        raise ValueError('Keyword count changed on reimport')
    for index, fields in expected:
        card = reloaded.keywords[index]
        for name,value in fields.items():
            if isinstance(card,str) or not equal(value,snapshot(card,name)):
                raise ValueError('Keyword field did not round-trip: '+str(index)+'.'+name)
    return {'backend':'pydyna','version':version('ansys-dyna-core'),'keyword_count':len(reloaded.keywords),
            'reimport_verified':True,'validation_summary':str(validation.get_summary()),
            'validation_scope':'PyDYNA registered validators and explicit-field round-trip; not solver or physical validation',
            'solver_validated':False,'native_validated':False}


class KeywordTools:
    def list_pydyna_keywords(self, query: str = '', offset: int = 0, limit: int = 50) -> dict:
        """Search installed PyDYNA keyword classes by Python class name; discoverability does not certify LS-PrePost/solver support."""
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('Invalid pagination')
        matches = [name for name in keyword_types() if query.casefold() in name.casefold()]
        return {'backend':'pydyna','version':version('ansys-dyna-core'),'total_matches':len(matches),
                'classes':matches[offset:offset+limit],'scope':'Installed class catalog; not validated feature coverage'}

    def describe_pydyna_keyword(self, class_name: str) -> dict:
        """Read actual installed keyword properties, table columns, defaults and field documentation. Rejects guessed constructor names elsewhere."""
        import numpy as np
        import pandas as pd
        from ansys.dyna.core.lib.series_card import SeriesCard
        cls = keyword_type(class_name)
        card = new_keyword(cls)
        fields = []
        for name,prop in properties(cls).items():
            try:
                value = getattr(card,name)
                field = {'name':name,'description':(prop.__doc__ or '').strip()[:1200]}
                if isinstance(value,pd.DataFrame):
                    field.update(kind='table',columns=[{'name':k,'dtype':str(v)} for k,v in value.dtypes.items()])
                elif isinstance(value,(list,np.ndarray,SeriesCard)):
                    field.update(kind='series')
                elif value is None or isinstance(value,(int,float,str,bool)):
                    field.update(kind='scalar',default=None if isinstance(value,float) and not math.isfinite(value) else value,
                                 annotation=str(prop.fget.__annotations__.get('return','')))
                else:
                    field.update(kind='unsupported_container',type=type(value).__name__)
                fields.append(field)
            except Exception as exc:
                fields.append({'name':name,'kind':'conditional','reason':str(exc)[:200]})
        return {'backend':'pydyna','version':version('ansys-dyna-core'),'class_name':class_name,
                'keyword':str(card.keyword),'subkeyword':str(card.subkeyword),'fields':fields,
                'native_validated':False,'scope':'Runtime schema, not physical parameter advice'}

    def compose_keyword_deck(self, cards: list[dict], units: str) -> dict:
        """Build a new standalone deck from [{class_name, fields, options?}], supporting actual scalar/table/series properties; validate and reimport explicit values. No raw code or solver run."""
        if not cards or len(cards)>500:
            raise ValueError('Provide 1..500 keyword specifications')
        def work(directory):
            Deck,_ = api()
            deck = Deck()
            expected = []
            for spec in cards:
                if not isinstance(spec,dict) or not set(spec)<= {'class_name','fields','options'}:
                    raise ValueError('Invalid keyword specification')
                cls = keyword_type(spec['class_name'])
                if str(cls.keyword).upper() in ('INCLUDE','PARAMETER','KEYWORD','END'):
                    raise ValueError('Include/parameter/control delimiters require a dedicated adapter')
                card = new_keyword(cls)
                options = spec.get('options',[])
                if not isinstance(options,list) or any(not isinstance(x,str) or not re.fullmatch(r'[A-Z0-9_]+',x) for x in options):
                    raise ValueError('Options must be explicit uppercase names')
                for option in options:
                    card.activate_option(option)
                assign(card,spec.get('fields',{}))
                expected.append((len(deck.keywords),{name:snapshot(card,name) for name in spec['fields']}))
                deck.append(card)
            output = directory/'model.k'
            data = export_verified(deck,output,expected)
            return data,[check_artifact(output,'keyword')]
        return self._post_job('compose_keyword_deck',dict(cards=cards,units=units),[],work)

    def update_keyword_fields(self, model: str, class_name: str, selector: dict,
                               fields: dict, units: str) -> dict:
        """Update exactly one parsed keyword selected by scalar properties, into a fresh deck; explicit fields must survive reimport."""
        cls = keyword_type(class_name)
        if not selector or any(k not in properties(cls) for k in selector):
            raise ValueError('Selector must use actual scalar keyword properties')
        selector = {k:scalar(v) for k,v in selector.items()}
        source = self.settings.input_path(model)
        def work(directory):
            deck = load_standalone(source)
            found = [(i,c) for i,c in enumerate(deck.keywords) if isinstance(c,cls)
                     and all(equal(getattr(c,k),v) for k,v in selector.items())]
            if len(found)!=1:
                raise ValueError('Selector must match exactly one keyword')
            index, card = found[0]
            assign(card,fields)
            output = directory/'model.k'
            data = export_verified(deck,output,[(index,{name:snapshot(card,name) for name in fields})])
            return data,[check_artifact(output,'keyword')]
        return self._post_job('update_keyword_fields',dict(class_name=class_name,selector=selector,fields=fields,units=units),[source],work)

    def update_keyword_table_row(self, model: str, class_name: str, table_name: str,
                                  selector: dict, values: dict, units: str) -> dict:
        """Update exactly one DataFrame row across parsed keyword blocks by explicit column equality; preserves original deck and reimport-checks the table."""
        import pandas as pd
        cls = keyword_type(class_name)
        if table_name not in properties(cls) or not selector or not values:
            raise ValueError('Table, selector and values required')
        source = self.settings.input_path(model)
        def work(directory):
            deck = load_standalone(source)
            found = []
            for index, card in enumerate(deck.keywords):
                if not isinstance(card,cls):
                    continue
                frame = getattr(card,table_name)
                if not isinstance(frame,pd.DataFrame) or not (set(selector)|set(values))<=set(frame.columns):
                    raise ValueError('Unknown table/columns')
                mask = pd.Series(True,index=frame.index)
                for key,val in selector.items():
                    mask &= frame[key] == scalar(val)
                found.extend((index,card,row) for row in frame.index[mask])
            if len(found)!=1:
                raise ValueError('Selector must identify exactly one table row')
            index,card,row = found[0]
            frame = getattr(card,table_name).copy()
            for key,val in values.items():
                frame.at[row,key] = scalar(val)
            setattr(card,table_name,frame)
            output = directory/'model.k'
            data = export_verified(deck,output,[(index,{table_name:snapshot(card,table_name)})])
            return data,[check_artifact(output,'keyword')]
        return self._post_job('update_keyword_table_row',dict(class_name=class_name,table_name=table_name,
                              selector=selector,values=values,units=units),[source],work)
