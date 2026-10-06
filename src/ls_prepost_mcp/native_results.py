"""Native SCL/command-file exports. Only staged copies are opened by LS-PrePost."""
import csv
import json
import re
import shutil

from .field_contracts import ELEMENT_SCALARS, FieldSpec, ResultSelection, SamplingSpec
from .jobs import atomic_json, fingerprint, now
from .native import commands as nc
from .post_backend import ids, write_csv
from .result_validity import load_physical_validity, reject_adaptive_family, scalar_statistics, validity_scope
from .runner import record_batch_result, run_batch
from .stress import CONVENTIONS, NULLABLE, native_mises_matches, stress_metrics

STRESS_KEYS = ["stress_x", "stress_y", "stress_z", "stress_xy", "stress_yz", "stress_zx"]
ELEMENT_FIELDS = set(STRESS_KEYS + ["von_mises", "effective_plastic_strain", "stress_1stprincipal",
    "stress_2ndprincipal", "stress_3rdprincipal", "strain_x", "strain_y", "strain_z", "strain_xy",
    "strain_yz", "strain_zx", "volume", "area", "thickness", "internal_energy_density"])
NODE_FIELDS = {"disp_x", "disp_y", "disp_z", "disp_magnitude", "velo_x", "velo_y", "velo_z",
               "accel_x", "accel_y", "accel_z", "state_node_x", "state_node_y", "state_node_z"}


STAGING_FILE_LIMIT = 1000
STAGING_BYTE_LIMIT = 2 * 1024**3


def input_family(settings, source, family=False):
    sources = [source]
    if family:
        sources += sorted(p for p in source.parent.iterdir()
                          if re.fullmatch(re.escape(source.name) + r"\d+", p.name))
    return [settings.input_path(str(p)) for p in sources]


def exceeds_staging_limit(sources):
    return len(sources) > STAGING_FILE_LIMIT or sum(p.stat().st_size for p in sources) > STAGING_BYTE_LIMIT


def stage(settings, source, directory, family=False):
    sources = input_family(settings, source, family)
    if exceeds_staging_limit(sources):
        raise ValueError("Native read-only staging limit: 1000 files / 2 GiB")
    before = [fingerprint(p) for p in sources]
    for p in sources:
        name = "d3plot" + p.name[len(source.name):] if family else "input_data"
        shutil.copyfile(p, directory / name)
        if fingerprint(p) != before[sources.index(p)]:
            raise ValueError("Input changed while staging")
    return sources, before


def finish_native(settings, jobs, action, parameters, source, build, parse, family=False, channel=None, executor=None):
    if not isinstance(parameters.get("units"), str) or not parameters["units"].strip():
        raise ValueError("An explicit unit-system label is required")
    directory, manifest = jobs.create(action, parameters)
    manifest.update(backend="lsprepost", native_channel=channel or ("scl" if family else "command_file"),
                    executable=fingerprint(settings.native_executable()))
    try:
        sources, before = stage(settings, source, directory, family)
        manifest["inputs"] = before
        build(directory)
        if executor is not None:
            executor(directory, manifest)
        else:
            execution = run_batch(settings.native_executable(), directory / "commands.cfile", directory,
                              timeout=settings.timeout, graphics=False, operation=manifest["action"])
            record_batch_result(execution, manifest, directory)
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


def field_script(domain, entity_ids, states, fields, ipt, output_path="native.csv"):
    kind = domain.upper()
    counter = "num_nodes" if domain == "node" else "num_" + domain + "_elements"
    declarations = "\n".join("Float *v%d=NULL;" % i for i in range(len(fields)))
    allocations = "\n".join("v%d=malloc(ne*sizeof(Float));" % i for i in range(len(fields)))
    loads = "\n".join('n=SCLGetDataCenterFloatArray("%s",%s,%s,&v%d);\nif(n!=ne) { fprintf(fp,"ERROR_%s,count_%%d_expected_%%d\\n",n,ne); fclose(fp); return; }' % (key, kind, "0" if key in ELEMENT_SCALARS else ipt, i, key)
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
    point_guard = ''
    if domain == 'solid' and ipt.isdigit() and int(ipt) > 0:
        point_guard = ('if(SCLGetDataCenterInt("is_full_integrated")!=1){fp=fopen('
                       + json.dumps(str(output_path).replace('\\', '/'), ensure_ascii=False)
                       + ',"w");if(fp!=NULL){fprintf(fp,"ERROR_SOLID_POINT_UNAVAILABLE\\n");fclose(fp);}return;}\n')
    return ('/*LS-SCRIPT*/\ndefine:\nvoid main(void)\n{\nInt ne,ns,n,j,uid;\nFILE *fp;\nFloat *times=NULL;\n'
            + declarations + '\n' + point_guard + 'ne=SCLGetDataCenterInt("' + counter + '");\nns=SCLGetDataCenterInt("num_states");\n'
            'if(ne<=0 || ns<=0) return;\ntimes=malloc(ns*sizeof(Float));\n'
            'n=SCLGetDataCenterFloatArray("state_times",0,0,&times);\nif(n!=ns) return;\n'
            + allocations + '\nfp=fopen(' + json.dumps(str(output_path).replace('\\', '/'), ensure_ascii=False) + ',"w");\nfprintf(fp,"state,time,entity_id,'
            + ",".join(fields) + '\\n");\n' + "\n".join(body) + '\nfclose(fp);\n' + frees + '\nfree(times);\n}\nmain();\n')


def native_fields(settings, jobs, source, domain, entity_ids, states, fields, integration_point, units, derived=False, executor=None,
                  validity_policy="raw"):
    if validity_policy == "alive" and source is not None:
        reject_adaptive_family(source)
    if domain not in ("shell", "solid", "tshell", "node"):
        raise ValueError("Native fields support node, shell, solid and tshell")
    ids(entity_ids, "entity_ids", 1000)
    ids(states, "states", 1000)
    if len(entity_ids)*len(states) > 100000:
        raise ValueError("Native export exceeds 100000 rows")
    allowed = NODE_FIELDS if domain == "node" else ELEMENT_FIELDS
    if not fields or len(fields) > 32 or len(set(fields)) != len(fields) or not set(fields) <= allowed:
        raise ValueError("Unsupported or duplicate native fields")
    sampling = SamplingSpec.native_fields(domain, integration_point, fields)
    ipt = sampling.native_selector
    spec = FieldSpec('lsprepost', tuple(fields), units,
                     ResultSelection(domain, entity_ids, states), sampling,
                     'native DataCenter component frame; no coordinate transformation',
                     'native field/layer definition; no additional averaging',
                     validity_scope(validity_policy))
    entity_ids, states, fields = list(spec.selection.entity_ids), list(spec.selection.states), list(spec.fields)
    params = dict(domain=domain, entity_ids=entity_ids, states=states, fields=fields,
                  integration_point=integration_point, units=units, field_spec=spec.describe(), validity_policy=validity_policy)
    validity = {}
    def build(directory, in_memory=False, validity_source=None):
        if validity_policy == "alive":
            mask_path = validity_source if in_memory else directory / "d3plot"
            if mask_path is None:
                raise ValueError("A verified staged result source is required for physical validity")
            validity["mask"] = load_physical_validity(mask_path, states, domain)
            validity["report"] = validity["mask"].describe(entity_ids, states)
            atomic_json(directory / "physical-validity.json", validity["report"])
        output = directory / "native.csv" if in_memory else "native.csv"
        nc.write_scl(directory / "extract.scl", field_script(domain, entity_ids, states, fields, ipt, output))
        commands = [nc.run_script(directory / "extract.scl", "scl")] if in_memory else ["new", nc.open_model("d3plot", "d3plot", openc=True), nc.run_script("extract.scl", "scl"), "exit"]
        nc.write_cfile(directory / "commands.cfile", commands)
        return validity.get("report")
    def parse(directory):
        with (directory / "native.csv").open(newline="", encoding="utf8") as f:
            if f.readline().startswith('ERROR_SOLID_POINT_UNAVAILABLE'):
                raise ValueError('Numbered solid points are unavailable in this native database; use the native default or output fully-integrated results')
            f.seek(0)
            rows = list(csv.DictReader(f))
        expected = {(s, uid) for s in states for uid in entity_ids}
        actual = [(int(r["state"]), int(r["entity_id"])) for r in rows]
        mask = validity.get("mask")
        needed = expected if mask is None else {(s, uid) for s, uid in expected if mask.alive(s, uid)}
        if not set(actual) <= expected or len(actual) != len(set(actual)) or not needed <= set(actual):
            raise ValueError("Native output did not contain exactly the requested state/user-ID matrix")
        raw_count = len(rows)
        if mask is not None:
            for row in rows:
                mask.check_time(int(row["state"]), float(row["time"]))
            rows = [r for r in rows if mask.alive(int(r["state"]), int(r["entity_id"]))]
        artifact = write_csv(directory / "results.csv", ["state", "time", "entity_id", *fields],
                             ([r[k] for k in ["state", "time", "entity_id", *fields]] for r in rows), allow_empty=mask is not None)
        data = {"backend": "lsprepost", "native_channel": "scl", "requires_python": False,
                "row_count": len(rows), "fields": fields, "integration_point": integration_point,
                "frame": "native DataCenter component frame; no coordinate transformation",
                "selection": "SCLGetUserId; native layer selection; no additional averaging",
                "read_only": "LS-PrePost opened staged copies only"}
        data['field_spec'] = spec.describe()
        data.update(validity_policy=validity_policy, validity=validity.get("report"),
                    physical_deletion_filter_applied=mask is not None,
                    unfiltered_native_row_count=raw_count, requested_row_count=len(expected),
                    excluded_deleted_count=len(expected)-len(needed) if mask is not None else None,
                    empty_reason="all_requested_entities_deleted" if not rows and mask is not None else None,
                    statistics=scalar_statistics(rows, fields))
        artifacts = [artifact]
        if derived:
            metric_rows = []
            names = list(stress_metrics([0]*6))
            errors = []
            for row in rows:
                metrics = stress_metrics([float(row[k]) for k in STRESS_KEYS])
                native_mises = float(row["von_mises"])
                if not native_mises_matches([float(row[k]) for k in STRESS_KEYS], metrics["von_mises"], native_mises):
                    raise ValueError("Six-component Mises disagrees with native von_mises; check layer/frame semantics")
                errors.append(abs(metrics["von_mises"]-native_mises))
                metric_rows.append([row["state"], row["time"], row["entity_id"], *[metrics[k] for k in names]])
            artifacts.append(write_csv(directory / "stress.csv", ["state", "time", "entity_id", *names], metric_rows, NULLABLE,
                                       allow_empty=mask is not None))
            data.update(conventions=CONVENTIONS, derived_backend="Python invariant mathematics on native SCL stresses",
                        native_mises_max_absolute_error=max(errors) if errors else None,
                        derived_statistics=scalar_statistics((dict(zip(["state", "time", "entity_id", *names], row)) for row in metric_rows), names))
        return data, artifacts
    if executor is not None:
        return executor("extract_native_stress" if derived else "extract_native_fields", params, build, parse)
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
        commands = ["new", 'ascii %s open "input_data" 0' % database,
                    'ascii %s plot %s' % (database, selector), nc.save_xypair("curve.xy"), "exit"]
        nc.write_cfile(directory / "commands.cfile", commands)
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


def native_binout(settings, jobs, source, branch, quantity, entity_id, units, executor=None):
    nodal = {q + '_' + axis.lower(): q.upper() + '_' + axis for q in ('displacement', 'velocity', 'acceleration', 'coordinate') for axis in ('X', 'Y', 'Z')}
    global_fields = {'kinetic_energy': 'KINETIC_ENERGY', 'internal_energy': 'INTERNAL_ENERGY',
                     'total_energy': 'TOTAL_ENERGY', 'external_work': 'EXTERNAL_WORK',
                     'hourglass_energy': 'HOURGLASS_ENERGY'}
    matsum = {q:q.upper() for q in ('internal_energy', 'kinetic_energy', 'eroded_internal_energy',
              'eroded_kinetic_energy', 'mass', 'hourglass_energy', 'momentum_x', 'momentum_y', 'momentum_z')}
    matsum.update({'rigid_body_velocity_'+axis.lower():'RBVELOCITY_'+axis for axis in ('X','Y','Z')})
    fields = {'nodout':nodal, 'glstat':global_fields, 'matsum':matsum}
    if branch not in fields or quantity not in fields[branch]:
        raise ValueError('Supported native binout branches: nodout components, glstat energies and matsum scalars')
    if branch in ('nodout', 'matsum'):
        ids([entity_id], 'entity_id')
    elif entity_id is not None:
        raise ValueError('GLSTAT has no entity ID')
    enum = 'BINOUT_' + branch.upper()
    quantity_enum = enum + '_' + fields[branch][quantity]
    def build(directory):
        script = ('/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nchar *h;\nBINOUT_Parameter p;\nInt n,ok,i,ni,found;\n'
                  'Int *uids=NULL;\nFloat *t=NULL;\nFloat *v=NULL;\nFILE *fp;\n'
                  'SCLBinoutInit(&p);\np.id=%d;\nh=SCLBinoutOpen(%s);\nif(h==NULL)return;\n' %
                  (entity_id or 0, json.dumps(str(directory/'input_data'))))
        if branch in ('nodout', 'matsum'):
            script += ('ok=SCLBinoutReadInt(h,%s_NUM_ID,&ni,&p);\nif(ok==0 || ni<=0 || ni>10000000){SCLBinoutClose(h);return;}\n'
                       'uids=malloc(ni*sizeof(Int));\nok=SCLBinoutReadIntArray(h,%s_IDS,&uids,&p);\n'
                       'if(ok==0){free(uids);SCLBinoutClose(h);return;}\nfound=0;\nfor(i=0;i<ni;i=i+1)if(uids[i]==p.id)found=1;\n'
                       'free(uids);\nif(found==0){SCLBinoutClose(h);return;}\n') % (enum,enum)
        script += ('ok=SCLBinoutReadInt(h,%s_NUM_TIMESTEP,&n,&p);\nif(ok==0 || n<=0 || n>1000000){SCLBinoutClose(h);return;}\n'
                   't=malloc(n*sizeof(Float));\nv=malloc(n*sizeof(Float));\n'
                   'ok=SCLBinoutReadFloatArray(h,%s_X,&t,&p);\nif(ok==0){free(t);free(v);SCLBinoutClose(h);return;}\n'
                   'ok=SCLBinoutReadFloatArray(h,%s,&v,&p);\nif(ok==0){free(t);free(v);SCLBinoutClose(h);return;}\n'
                   'fp=fopen(%s,"w");\nif(fp==NULL){free(t);free(v);SCLBinoutClose(h);return;}\nfprintf(fp,"time,value\\n");\n'
                   'for(i=0;i<n;i=i+1)fprintf(fp,"%%.17g,%%.17g\\n",t[i],v[i]);\n'
                   'fclose(fp);\nSCLBinoutClose(h);\nfree(t);\nfree(v);\n}\nmain();\n') % (
                       enum, enum, quantity_enum, json.dumps((directory/'native.csv').as_posix()))
        nc.write_scl(directory/'binout.scl', script)
        nc.write_cfile(directory/'commands.cfile', ["new", nc.run_script("binout.scl", "scl"), "exit"])
    def parse(directory):
        import math

        if not (directory/'native.csv').exists():
            raise ValueError('Native Binout did not produce the requested curve; verify branch, stored ID, quantity and runtime log')
        with (directory/'native.csv').open(newline='') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames != ['time','value']:
                raise ValueError('Invalid native Binout curve columns')
            rows = [[float(r['time']),float(r['value'])] for r in reader]
        if len(rows)<2 or any(not math.isfinite(v) for row in rows for v in row) or any(rows[i][0]<=rows[i-1][0] for i in range(1,len(rows))):
            raise ValueError('Native Binout requires at least2 finite samples and a strictly increasing time axis')
        artifact = write_csv(directory/'curve.csv', ['time','value'], rows)
        return {'backend':'lsprepost','native_channel':'scl_binout','branch':branch,'quantity':quantity,
                'entity_id':entity_id,'row_count':len(rows),'requires_python':executor is not None,
                'entity_scope':'stored Binout branch ID; no implicit association with the displayed model',
                'units':units,'units_inferred':False}, [artifact]
    return finish_native(settings,jobs,'extract_native_binout_curve',
                         dict(branch=branch,quantity=quantity,entity_id=entity_id,units=units),source,build,parse,
                         channel='scl_binout',executor=executor)
