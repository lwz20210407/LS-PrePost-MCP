"""Native SCL/command-file exports. Only staged copies are opened by LS-PrePost."""
import csv
import math
import re
import shutil

from .field_contracts import FieldSpec, ResultSelection, SamplingSpec
from .jobs import atomic_json, fingerprint, now
from .post_backend import ids, write_csv
from .runner import execute
from .stress import CONVENTIONS, NULLABLE, stress_metrics

STRESS_KEYS = ["stress_x", "stress_y", "stress_z", "stress_xy", "stress_yz", "stress_zx"]
ELEMENT_FIELDS = set(STRESS_KEYS + ["von_mises", "effective_plastic_strain", "stress_1stprincipal",
    "stress_2ndprincipal", "stress_3rdprincipal", "strain_x", "strain_y", "strain_z", "strain_xy",
    "strain_yz", "strain_zx", "volume", "area", "thickness", "internal_energy_density"])
NODE_FIELDS = {"disp_x", "disp_y", "disp_z", "disp_magnitude", "velo_x", "velo_y", "velo_z",
               "accel_x", "accel_y", "accel_z", "state_node_x", "state_node_y", "state_node_z"}


def stage(settings, source, directory, family=False):
    sources = [source]
    if family:
        sources += sorted(p for p in source.parent.iterdir()
                          if re.fullmatch(re.escape(source.name) + r"\d+", p.name))
    sources = [settings.input_path(str(p)) for p in sources]
    if len(sources) > 1000 or sum(p.stat().st_size for p in sources) > 2*1024**3:
        raise ValueError("Native read-only staging limit: 1000 files / 2 GiB")
    before = [fingerprint(p) for p in sources]
    for p in sources:
        name = "d3plot" + p.name[len(source.name):] if family else "input_data"
        shutil.copyfile(p, directory / name)
        if fingerprint(p) != before[sources.index(p)]:
            raise ValueError("Input changed while staging")
    return sources, before


def finish_native(settings, jobs, action, parameters, source, build, parse, family=False, channel=None):
    if not isinstance(parameters.get("units"), str) or not parameters["units"].strip():
        raise ValueError("An explicit unit-system label is required")
    directory, manifest = jobs.create(action, parameters)
    manifest.update(backend="lsprepost", native_channel=channel or ("scl" if family else "command_file"),
                    executable=fingerprint(settings.native_executable()))
    try:
        sources, before = stage(settings, source, directory, family)
        manifest["inputs"] = before
        build(directory)
        process = execute(settings.native_executable(), directory / "commands.cfile", directory,
                          timeout=settings.timeout, graphics=False)
        manifest["process"] = process
        if process["returncode"] != 0 or process["timed_out"]:
            raise RuntimeError("Native result export failed or timed out")
        data, artifacts = parse(directory)
        if [fingerprint(p) for p in sources] != before:
            raise ValueError("Original inputs changed during native export")
        manifest.update(status="succeeded", data=data, artifacts=artifacts)
    except Exception as exc:
        manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
    manifest.update(finished_at=now(), job_directory=str(directory),
                    logs=[str(p) for p in directory.glob("*.log")] + [str(p) for p in directory.glob("lspost.*")])
    atomic_json(directory / "job.json", manifest)
    return manifest


def field_script(domain, entity_ids, states, fields, ipt):
    kind = domain.upper()
    counter = "num_nodes" if domain == "node" else "num_" + domain + "_elements"
    declarations = "\n".join("Float *v%d=NULL;" % i for i in range(len(fields)))
    allocations = "\n".join("v%d=malloc(ne*sizeof(Float));" % i for i in range(len(fields)))
    loads = "\n".join('n=SCLGetDataCenterFloatArray("%s",%s,%s,&v%d);\nif(n!=ne) { fprintf(fp,"ERROR_%s,count_%%d_expected_%%d\\n",n,ne); fclose(fp); return; }' % (key, kind, ipt, i, key)
                      for i, key in enumerate(fields))
    selects = " || ".join("uid==%d" % uid for uid in entity_ids)
    body = []
    fmt = "%d,%.17g,%d" + ",%.17g" * len(fields) + "\\n"
    arguments = ",".join("v%d[j]" % i for i in range(len(fields)))
    for state in states:
        body.append('if(ns<%d) { fclose(fp); return; }\nSCLSwitchStateTo(%d);\n%s\n'
                    'for(j=0;j<ne;j=j+1){\nuid=SCLGetUserId(j,%s);\nif(%s) fprintf(fp,"%s",%d,times[%d],uid,%s);\n}'
                    % (state, state, loads, kind, selects, fmt, state, state-1, arguments))
    frees = "\n".join("free(v%d);" % i for i in range(len(fields)))
    return ('/*LS-SCRIPT*/\ndefine:\nvoid main(void)\n{\nInt ne,ns,n,j,uid;\nFILE *fp;\nFloat *times=NULL;\n'
            + declarations + '\nne=SCLGetDataCenterInt("' + counter + '");\nns=SCLGetDataCenterInt("num_states");\n'
            'if(ne<=0 || ns<=0) return;\ntimes=malloc(ns*sizeof(Float));\n'
            'n=SCLGetDataCenterFloatArray("state_times",0,0,&times);\nif(n!=ns) return;\n'
            + allocations + '\nfp=fopen("native.csv","w");\nfprintf(fp,"state,time,entity_id,'
            + ",".join(fields) + '\\n");\n' + "\n".join(body) + '\nfclose(fp);\n' + frees + '\nfree(times);\n}\nmain();\n')


def native_fields(settings, jobs, source, domain, entity_ids, states, fields, integration_point, units, derived=False):
    if domain not in ("shell", "solid", "tshell", "node"):
        raise ValueError("Native fields support node, shell, solid and tshell")
    ids(entity_ids, "entity_ids", 1000)
    ids(states, "states", 1000)
    if len(entity_ids)*len(states) > 100000:
        raise ValueError("Native export exceeds 100000 rows")
    allowed = NODE_FIELDS if domain == "node" else ELEMENT_FIELDS
    if not fields or len(fields) > 32 or len(set(fields)) != len(fields) or not set(fields) <= allowed:
        raise ValueError("Unsupported or duplicate native fields")
    sampling = SamplingSpec.native(domain, integration_point)
    ipt = sampling.native_selector
    spec = FieldSpec('lsprepost', tuple(fields), units,
                     ResultSelection(domain, entity_ids, states), sampling,
                     'native DataCenter component frame; no coordinate transformation',
                     'native field/layer definition; no additional averaging',
                     'native field population; no explicit alive/deletion filtering')
    entity_ids, states, fields = list(spec.selection.entity_ids), list(spec.selection.states), list(spec.fields)
    params = dict(domain=domain, entity_ids=entity_ids, states=states, fields=fields,
                  integration_point=integration_point, units=units, field_spec=spec.describe())
    def build(directory):
        (directory / "extract.scl").write_text(field_script(domain, entity_ids, states, fields, ipt), encoding="ascii")
        (directory / "commands.cfile").write_text('new\nopenc d3plot "d3plot"\nrunscript extract.scl\nexit\n', encoding="ascii")
    def parse(directory):
        with (directory / "native.csv").open(newline="", encoding="utf8") as f:
            rows = list(csv.DictReader(f))
        expected = {(s, uid) for s in states for uid in entity_ids}
        actual = [(int(r["state"]), int(r["entity_id"])) for r in rows]
        if set(actual) != expected or len(actual) != len(expected):
            raise ValueError("Native output did not contain exactly the requested state/user-ID matrix")
        artifact = write_csv(directory / "results.csv", ["state", "time", "entity_id", *fields],
                             ([r[k] for k in ["state", "time", "entity_id", *fields]] for r in rows))
        data = {"backend": "lsprepost", "native_channel": "scl", "requires_python": False,
                "row_count": len(rows), "fields": fields, "integration_point": integration_point,
                "frame": "native DataCenter component frame; no coordinate transformation",
                "selection": "SCLGetUserId; native layer selection; no additional averaging",
                "read_only": "LS-PrePost opened staged copies only"}
        data['field_spec'] = spec.describe()
        artifacts = [artifact]
        if derived:
            metric_rows = []
            names = list(stress_metrics([0]*6))
            errors = []
            for row in rows:
                metrics = stress_metrics([float(row[k]) for k in STRESS_KEYS])
                native_mises = float(row["von_mises"])
                if not math.isclose(metrics["von_mises"], native_mises, rel_tol=2e-4, abs_tol=1e-6):
                    raise ValueError("Six-component Mises disagrees with native von_mises; check layer/frame semantics")
                errors.append(abs(metrics["von_mises"]-native_mises))
                metric_rows.append([row["state"], row["time"], row["entity_id"], *[metrics[k] for k in names]])
            artifacts.append(write_csv(directory / "stress.csv", ["state", "time", "entity_id", *names], metric_rows, NULLABLE))
            data.update(conventions=CONVENTIONS, derived_backend="Python invariant mathematics on native SCL stresses",
                        native_mises_max_absolute_error=max(errors))
        return data, artifacts
    return finish_native(settings, jobs, "extract_native_stress" if derived else "extract_native_fields",
                         params, source, build, parse, family=True)


def native_ascii(settings, jobs, source, database, component, entity_id, units):
    if database not in ("glstat", "nodout", "matsum", "spcforc", "secforc", "rbdout"):
        raise ValueError("Unsupported native ASCII database")
    ids([component], "component", 1000)
    if component > 1000:
        raise ValueError("ASCII component code must be 1..1000")
    if database == "glstat" and entity_id is not None:
        raise ValueError("GLSTAT has no entity ID")
    if database != "glstat":
        ids([entity_id], "entity_id")
    def build(directory):
        selector = str(component) + (" " + str(entity_id) if entity_id is not None else "")
        commands = 'new\nascii %s open "input_data" 0\nascii %s plot %s\nxyplot 1 savefile xypair "curve.xy" 1 all\nexit\n' % (database, database, selector)
        (directory / "commands.cfile").write_text(commands, encoding="ascii")
    def parse(directory):
        rows = []
        with (directory / "curve.xy").open(encoding="utf8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    try:
                        rows.append([float(x.replace("D", "E")) for x in parts])
                    except ValueError:
                        continue
        if len(rows) < 2 or any(rows[i][0] <= rows[i-1][0] for i in range(1, len(rows))):
            raise ValueError("Native curve missing or has non-increasing time (multiple curves/invalid selection)")
        artifact = write_csv(directory / "curve.csv", ["time", "value"], rows)
        return {"backend": "lsprepost", "native_channel": "command_file", "database": database,
                "component_code": component, "entity_id": entity_id, "row_count": len(rows),
                "component_semantics": "LS-PrePost ASCII dialog component number; version-specific",
                "read_only": "LS-PrePost opened staged copy only"}, [artifact]
    return finish_native(settings, jobs, "extract_native_ascii_curve",
                         dict(database=database, component=component, entity_id=entity_id, units=units), source, build, parse)


def native_binout(settings, jobs, source, branch, quantity, entity_id, units):
    nodal = {q + '_' + axis.lower(): q.upper() + '_' + axis for q in ('displacement', 'velocity', 'acceleration', 'coordinate') for axis in ('X', 'Y', 'Z')}
    global_fields = {'kinetic_energy': 'KINETIC_ENERGY', 'internal_energy': 'INTERNAL_ENERGY',
                     'total_energy': 'TOTAL_ENERGY', 'external_work': 'EXTERNAL_WORK',
                     'hourglass_energy': 'HOURGLASS_ENERGY'}
    if branch not in ('nodout', 'glstat') or quantity not in (nodal if branch == 'nodout' else global_fields):
        raise ValueError('Supported native binout branches: nodout components and glstat energies')
    if branch == 'nodout':
        ids([entity_id], 'entity_id')
    elif entity_id is not None:
        raise ValueError('GLSTAT has no entity ID')
    enum = 'BINOUT_' + branch.upper()
    quantity_enum = enum + '_' + (nodal if branch == 'nodout' else global_fields)[quantity]
    def build(directory):
        script = ('/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nchar *h;\nBINOUT_Parameter p;\nInt n,ok,i,ni,found;\n'
                  'Int *uids=NULL;\nFloat *t=NULL;\nFloat *v=NULL;\nFILE *fp;\n'
                  'SCLBinoutInit(&p);\np.id=%d;\nh=SCLBinoutOpen("input_data");\n' % (entity_id or 0))
        if branch == 'nodout':
            script += ('ok=SCLBinoutReadInt(h,BINOUT_NODOUT_NUM_ID,&ni,&p);\nif(ok==0 || ni<=0)return;\n'
                       'uids=malloc(ni*sizeof(Int));\nok=SCLBinoutReadIntArray(h,BINOUT_NODOUT_IDS,&uids,&p);\n'
                       'if(ok==0)return;\nfound=0;\nfor(i=0;i<ni;i=i+1)if(uids[i]==p.id)found=1;\n'
                       'free(uids);\nif(found==0)return;\n')
        script += ('ok=SCLBinoutReadInt(h,%s_NUM_TIMESTEP,&n,&p);\nif(ok==0 || n<=0 || n>1000000)return;\n'
                   't=malloc(n*sizeof(Float));\nv=malloc(n*sizeof(Float));\n'
                   'ok=SCLBinoutReadFloatArray(h,%s_X,&t,&p);\nif(ok==0)return;\n'
                   'ok=SCLBinoutReadFloatArray(h,%s,&v,&p);\nif(ok==0)return;\n'
                   'fp=fopen("native.csv","w");\nfprintf(fp,"time,value\\n");\n'
                   'for(i=0;i<n;i=i+1)fprintf(fp,"%%.17g,%%.17g\\n",t[i],v[i]);\n'
                   'fclose(fp);\nSCLBinoutClose(h);\nfree(t);\nfree(v);\n}\nmain();\n') % (enum, enum, quantity_enum)
        (directory/'binout.scl').write_text(script, encoding='ascii')
        (directory/'commands.cfile').write_text('new\nrunscript binout.scl\nexit\n', encoding='ascii')
    def parse(directory):
        with (directory/'native.csv').open(newline='') as f:
            rows = list(csv.DictReader(f))
        artifact = write_csv(directory/'curve.csv', ['time','value'], ([r['time'],r['value']] for r in rows))
        return {'backend':'lsprepost','native_channel':'scl_binout','branch':branch,'quantity':quantity,
                'entity_id':entity_id,'row_count':len(rows),'requires_python':False}, [artifact]
    return finish_native(settings,jobs,'extract_native_binout_curve',
                         dict(branch=branch,quantity=quantity,entity_id=entity_id,units=units),source,build,parse,channel='scl_binout')
