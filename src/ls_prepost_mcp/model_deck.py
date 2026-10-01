"""Scoped structural checks and parameterized preprocessing with modern PyDYNA."""
import math
from collections import Counter

from .deck_backend import api


def load_standalone(path):
    Deck, _ = api()
    text = path.read_text(errors='replace')
    if any(s.strip().upper().startswith(('*INCLUDE', '*PARAMETER')) for s in text.splitlines()):
        raise ValueError('This operation requires a standalone deck without includes/parameters')
    deck = Deck()
    deck.import_file(str(path))
    return deck


def table(deck, cls, attr):
    import pandas as pd
    frames = [getattr(c, attr) for c in deck.keywords if isinstance(c, cls)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def validate_references(path):
    _, kw = api()
    deck = load_standalone(path)
    nodes = table(deck, kw.Node, 'nodes')
    parts = table(deck, kw.Part, 'parts')
    errors, warnings = [], []
    registries = {}
    def register(name, values):
        numbers = [int(x) for x in values]
        duplicates = [i for i, count in Counter(numbers).items() if count > 1]
        if duplicates:
            errors.append({'kind':'duplicate_id','entity':name,'ids':duplicates[:100]})
        if any(i <= 0 for i in numbers):
            errors.append({'kind':'nonpositive_id','entity':name})
        registries[name] = set(numbers)
    register('node', nodes['nid'] if len(nodes) else [])
    register('part', parts['pid'] if len(parts) else [])
    register('material', [c.mid for c in deck.keywords if not isinstance(c,str) and c.keyword=='MAT' and getattr(c,'mid',None) is not None])
    register('section', [c.secid for c in deck.keywords if not isinstance(c,str) and c.keyword=='SECTION' and getattr(c,'secid',None) is not None])
    register('node_set', [c.sid for c in deck.keywords if isinstance(c,kw.SetNodeList)])
    register('curve', [c.lcid for c in deck.keywords if isinstance(c,kw.DefineCurve)])
    def references(entity, owner, target, values):
        missing = sorted(set(int(v) for v in values) - registries[target])
        if missing:
            errors.append({'kind':'missing_reference','entity':entity,'owner_id':int(owner),'target':target,'ids':missing[:100]})
    if len(nodes) and not all(math.isfinite(float(v)) for v in nodes[['x','y','z']].to_numpy().flat):
        errors.append({'kind':'nonfinite_coordinates'})
    for _, row in parts.iterrows():
        references('part',row['pid'],'material',[row['mid']])
        references('part',row['pid'],'section',[row['secid']])
    for cls, kind, count in [(kw.ElementShell,'shell',4),(kw.ElementSolid,'solid',8),(kw.ElementBeam,'beam',2)]:
        elements = table(deck,cls,'elements')
        register(kind,elements['eid'] if len(elements) else [])
        for _, row in elements.iterrows():
            references(kind,row['eid'],'part',[row['pid']])
            references(kind,row['eid'],'node',[row['n'+str(i)] for i in range(1,count+1) if int(row['n'+str(i)]) != 0])
    for card in deck.keywords:
        if isinstance(card,kw.SetNodeList):
            # Native export pads the final node-list row with zero (no entity).
            references('node_set',card.sid,'node',[n for n in card.nodes if int(n) != 0])
        if isinstance(card,(kw.BoundarySpcSet,kw.BoundaryPrescribedMotionSet)):
            references('boundary',card.nsid,'node_set',[card.nsid])
        if isinstance(card,kw.BoundaryPrescribedMotionSet):
            references('motion',card.nsid,'curve',[card.lcid])
        if isinstance(card,str):
            warnings.append('Unparsed raw keyword block; not structurally validated')
        elif card.keyword in ('ELEMENT','NODE','PART','SET') and not isinstance(card,(kw.ElementShell,kw.ElementSolid,kw.ElementBeam,kw.Node,kw.Part,kw.SetNodeList)):
            warnings.append('Unsupported structural card: '+card.keyword+'_'+card.subkeyword)
    return {'backend':'pydyna','valid_within_scope':not errors,'errors':errors[:200],
            'error_count':len(errors),'counts':{key:len(value) for key,value in registries.items()},
            'warnings':sorted(set(warnings)),'solver_validated':False,
            'scope':'IDs and references for standard Node, Part, Shell/Solid/Beam, material, section, node-list sets, set boundaries and curves; no mesh quality/solver/physics validation'}


def add_box_set(source, output, set_id, bounds, tolerance):
    import numpy as np
    _, kw = api()
    deck = load_standalone(source)
    if any(getattr(c,'sid',None)==set_id and getattr(c,'keyword',None)=='SET' and str(c.subkeyword).startswith('NODE') for c in deck.keywords):
        raise ValueError('Node set ID already exists')
    nodes = table(deck,kw.Node,'nodes')
    if nodes.empty:
        raise ValueError('No standard NODE coordinates found')
    positions = nodes[['x','y','z']].to_numpy(dtype=float)
    lower, upper = np.asarray(bounds[:3]), np.asarray(bounds[3:])
    if not np.isfinite(positions).all():
        raise ValueError('Nonfinite node coordinates')
    mask = ((positions >= lower-tolerance) & (positions <= upper+tolerance)).all(axis=1)
    selected = [int(i) for i in nodes.loc[mask,'nid']]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError('Empty/duplicate-ID node selection')
    deck.append(kw.SetNodeList(sid=set_id,nodes=selected))
    deck.export_file(str(output))
    reloaded = load_standalone(output)
    found = [c for c in reloaded.keywords if isinstance(c,kw.SetNodeList) and c.sid==set_id]
    if len(found)!=1 or list(found[0].nodes)!=selected:
        raise ValueError('Node set did not survive export/reimport')
    return {'set_id':set_id,'node_count':len(selected),'node_id_sample':selected[:100],
            'coordinate_frame':'reference global','reimport_verified':True,'backend':'pydyna'}


def complete_tensile_plate(mesh, output, thickness, material, displacement, duration, interval):
    import numpy as np
    import pandas as pd
    Deck, kw = api()
    original = load_standalone(mesh)
    nodes = table(original,kw.Node,'nodes')
    elements = table(original,kw.ElementShell,'elements')
    if nodes.empty or elements.empty or len(set(elements['pid'])) != 1:
        raise ValueError('Expected a single-part shell plate mesh')
    pid = int(elements['pid'].iloc[0])
    xs = nodes['x'].to_numpy(float)
    tolerance = max(float(xs.max()-xs.min())*1e-9,1e-12)
    left = [int(v) for v in nodes.loc[np.abs(xs-xs.min())<=tolerance,'nid']]
    right = [int(v) for v in nodes.loc[np.abs(xs-xs.max())<=tolerance,'nid']]
    if set(left)&set(right):
        raise ValueError('Plate has no X extent')
    deck = Deck()
    # This function is only used on a fresh native generated mesh, never a user analysis deck.
    node_card, element_card = kw.Node(), kw.ElementShell()
    node_card.nodes = nodes.copy()
    element_card.elements = elements.copy()
    deck.extend([node_card, element_card])
    part = kw.Part()
    part.parts = pd.DataFrame([dict(heading='Prescribed-displacement shell plate',pid=pid,secid=1,mid=1)])
    section = kw.SectionShell(secid=1,elform=16,nip=3,t1=thickness,t2=thickness,t3=thickness,t4=thickness)
    curve = kw.DefineCurve(lcid=1)
    t = np.linspace(0,duration,101)
    u = displacement*(3*(t/duration)**2-2*(t/duration)**3)
    curve.curves = pd.DataFrame({'a1':t,'o1':u})
    deck.extend([part,section,kw.Mat001(mid=1,**material),
                 kw.SetNodeList(sid=1,nodes=left),kw.SetNodeList(sid=2,nodes=right),
                 kw.SetNodeList(sid=3,nodes=[int(v) for v in nodes['nid']]),
                 kw.BoundarySpcSet(nsid=1,dofx=1,dofy=1),
                 kw.BoundarySpcSet(nsid=3,dofz=1,dofrx=1,dofry=1),
                 kw.BoundaryPrescribedMotionSet(nsid=2,dof=1,vad=2,lcid=1),curve,
                 kw.ControlTermination(endtim=duration),kw.DatabaseBinaryD3Plot(dt=interval),
                 kw.DatabaseExtentBinary(strflg=1,maxint=3),kw.DatabaseGlstat(dt=interval),
                 kw.DatabaseMatsum(dt=interval),kw.DatabaseNodout(dt=interval),
                 kw.DatabaseHistoryNodeSet(id1=1,id2=2)])
    deck.export_file(str(output))
    checks = validate_references(output)
    if not checks['valid_within_scope']:
        raise ValueError('Generated plate has invalid references: '+str(checks['errors']))
    return {'backend':'native_mesh+pydyna','node_count':len(nodes),'shell_count':len(elements),
            'left_edge_nodes':len(left),'right_edge_nodes':len(right),'references':checks,
            'analysis':'explicit prescribed displacement, planar shell deformation, cubic smooth ramp',
            'solver_validated':False,'quasistatic_validated':False,
            'note':'Duration is user-selected; verify kinetic/internal energy and mesh convergence before interpreting quasi-static behavior'}
