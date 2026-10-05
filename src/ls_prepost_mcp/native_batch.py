"""Native result-database acceptance workflow; no solver and no source writes."""
import csv
import re
import shutil
from pathlib import Path

from .jobs import atomic_json, check_artifact, fingerprint, now
from .native_results import STRESS_KEYS
from .post_backend import write_csv
from .runner import execute
from .stress import CONVENTIONS, NULLABLE, stress_metrics

FIELDS = {
    "solid": STRESS_KEYS + ["von_mises", "effective_plastic_strain", "strain_x", "strain_y", "strain_z", "strain_xy", "strain_yz", "strain_zx"],
    "shell": STRESS_KEYS + ["von_mises", "effective_plastic_strain", "thickness"],
    "node": ["disp_x", "disp_y", "disp_z", "velo_x", "velo_y", "velo_z", "accel_x", "accel_y", "accel_z"],
}


def batch_script():
    declarations, setup, steps, closing = [], [], [], []
    for domain, fields in FIELDS.items():
        prefix = domain
        counter = "num_nodes" if domain == "node" else "num_" + domain + "_elements"
        declarations.append('Int %sn;\nFloat *%sv=NULL;' % (prefix, prefix))
        setup.append('%sn=SCLGetDataCenterInt("%s");\nif(%sn>0) %sv=malloc(%sn*sizeof(Float));' % (prefix, counter, prefix, prefix, prefix))
        for index, field in enumerate(fields):
            handle = prefix + str(index)
            declarations.append('FILE *%s;' % handle)
            declarations.append('FILE *%sh;' % handle)
            setup.append('%s=fopen("%s_%s.csv","w");\nfprintf(%s,"state,time,entity_id,value\\n");' % (handle, domain, field, handle))
            setup.append('%sh=fopen("%s_%s_extrema.csv","w");\nfprintf(%sh,"state,time,minimum,maximum,mean,min_entity_id,max_entity_id\\n");' % (handle, domain, field, handle))
            ipt = "MID" if domain == "shell" else "0"
            # Three representative user IDs per domain: first/middle/last geometry records.
            steps.append('if(%sn>0){\nn=SCLGetDataCenterFloatArray("%s",%s,%s,&%sv);\n'
                         'if(n==%sn){\nmn=%sv[0];mx=mn;total=0;imin=0;imax=0;\n'
                         'for(i=0;i<n;i=i+1){\nif(%sv[i]<mn){mn=%sv[i];imin=i;}\nif(%sv[i]>mx){mx=%sv[i];imax=i;}\ntotal=total+%sv[i];\n}\n'
                         'fprintf(%sh,"%%d,%%.17g,%%.17g,%%.17g,%%.17g,%%d,%%d\\n",st,times[st-1],mn,mx,total/n,SCLGetUserId(imin,%s),SCLGetUserId(imax,%s));\n'
                         'for(k=0;k<3;k=k+1){\nj=0;\nif(k==1)j=%sn/2;\nif(k==2)j=%sn-1;\n'
                         'uid=SCLGetUserId(j,%s);\nfprintf(%s,"%%d,%%.17g,%%d,%%.17g\\n",st,times[st-1],uid,%sv[j]);\n}\n}'
                         'else fprintf(diag,"%s,%s,%%d,%%d,%%d\\n",st,n,%sn);\n}'
                         % (prefix, field, domain.upper(), ipt, prefix, prefix, prefix,
                            prefix, prefix, prefix, prefix, prefix, handle, domain.upper(), domain.upper(), prefix, prefix,
                            domain.upper(), handle, prefix, domain, field, prefix))
            closing.append('fclose(%s);' % handle)
            closing.append('fclose(%sh);' % handle)
        closing.append('if(%sn>0)free(%sv);' % (prefix, prefix))
    return ('/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nInt ns,st,n,j,k,uid,i,imin,imax;\nFloat mn,mx,total;\nFloat *times=NULL;\nFILE *info;\nFILE *diag;\n'
            + "\n".join(declarations) + '\nns=SCLGetDataCenterInt("num_states");\nif(ns<=0)return;\n'
            'times=malloc(ns*sizeof(Float));\nn=SCLGetDataCenterFloatArray("state_times",0,0,&times);\nif(n!=ns)return;\n'
            + "\n".join(setup) + '\ninfo=fopen("inventory.txt","w");\nfprintf(info,"%d %d %d %d\\n",noden,solidn,shelln,ns);\n'
            'fclose(info);\ndiag=fopen("unavailable.csv","w");\nfprintf(diag,"domain,field,state,returned,expected\\n");\n'
            'for(st=1;st<=ns;st=st+1){\nSCLSwitchStateTo(st);\n' + "\n".join(steps) + '\n}\n'
            + "\n".join(closing) + '\nfclose(diag);\nfree(times);\n}\nmain();\n')


def read_native_xy(path):
    rows = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                try:
                    rows.append([float(x.replace("D", "E")) for x in parts])
                except ValueError:
                    continue
    if len(rows) < 2 or any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError("Missing or ambiguous native curve")
    return rows


def run_case(settings, jobs, source: Path, units: str):
    directory, manifest = jobs.create("native_postprocess_case", {"source": str(source), "units": units})
    manifest.update(backend="lsprepost", executable=fingerprint(settings.native_executable()), checks=[])
    created_copies = []
    try:
        family = [source] + sorted(p for p in source.parent.iterdir()
                                  if re.fullmatch(re.escape(source.name) + r"\d+", p.name))
        sources = [settings.input_path(str(p)) for p in family]
        ascii_files = [settings.input_path(str(p)) for p in source.parent.iterdir()
                       if p.is_file() and p.name in ("glstat", "nodout", "matsum", "spcforc", "rcforc", "elout", "rbdout", "secforc")]
        if len(sources) > 1000 or sum(p.stat().st_size for p in sources) > 4*1024**3:
            raise ValueError("One case exceeds staging limit (4 GiB/1000 files)")
        original = [fingerprint(p) for p in sources + ascii_files]
        manifest["inputs"] = original
        for p in sources + ascii_files:
            target = directory / ("d3plot" + p.name[len(source.name):] if p in sources else p.name)
            shutil.copyfile(p, target)
            created_copies.append(target)
        (directory / "extract.scl").write_text(batch_script(), encoding="ascii")
        commands = ['new', 'openc d3plot "d3plot"', 'runscript extract.scl']
        curves = []
        if (directory / "glstat").exists():
            for component in (1, 2):
                name = 'glstat_%d' % component
                commands += ['ascii glstat open "glstat" 0', 'ascii glstat plot %d' % component,
                             'xyplot 1 savefile xypair "%s.xy" 1 all' % name, 'deletewin 1']
                curves.append(name)
        if (directory / "nodout").exists():
            with (directory / "nodout").open(errors="replace") as f:
                head = ''.join(next(f, '') for _ in range(80))
            legend = re.search(r'\{BEGIN LEGEND\}(.*?)\{END LEGEND\}', head, re.S)
            node_ids = re.findall(r'^\s*(\d+)\s+\S', legend[1], re.M) if legend else []
            for node in node_ids[:2]:
                for component in (1, 2, 3, 5, 6, 7, 9, 10, 11):
                    name = 'nodout_%s_%d' % (node, component)
                    commands += ['ascii nodout open "nodout" 0', 'ascii nodout plot %d %s' % (component, node),
                                 'xyplot 1 savefile xypair "%s.xy" 1 all' % name, 'deletewin 1']
                    curves.append(name)
        if (directory / "matsum").exists():
            with (directory / "matsum").open(errors="replace") as f:
                head = ''.join(next(f, '') for _ in range(80))
            legend = re.search(r'\{BEGIN LEGEND\}(.*?)\{END LEGEND\}', head, re.S)
            part_ids = re.findall(r'^\s*(\d+)\s+\S', legend[1], re.M) if legend else []
            for part in part_ids[:3]:
                for component in (1, 2):
                    name = 'matsum_%s_%d' % (part, component)
                    commands += ['ascii matsum open "matsum" 0', 'ascii matsum plot %d %s' % (component, part),
                                 'xyplot 1 savefile xypair "%s.xy" 1 all' % name, 'deletewin 1']
                    curves.append(name)
        commands += ['exit']
        (directory / "commands.cfile").write_text('\n'.join(commands)+'\n', encoding="ascii")
        result = execute(settings.native_executable(), directory / "commands.cfile", directory,
                         timeout=settings.timeout, graphics=False)
        manifest["process"] = result
        if result.get("engine_status") == "failed" or result["returncode"] != 0 or result["timed_out"]:
            raise RuntimeError("Native batch process failed/timed out")
        nodes, solids, shells, states = map(int, (directory / "inventory.txt").read_text().split())
        manifest["counts"] = dict(nodes=nodes, solids=solids, shells=shells, states=states)
        field_rows = {}
        for domain, fields in FIELDS.items():
            count = {"node": nodes, "solid": solids, "shell": shells}[domain]
            if count == 0:
                continue
            for field in fields:
                name = domain + '_' + field
                try:
                    with (directory / (name+'.csv')).open(newline="") as f:
                        rows = list(csv.DictReader(f))
                    if len(rows) != states*3:
                        raise ValueError("Not all requested states/entities returned")
                    artifact = check_artifact(directory / (name+'.csv'), "csv")
                    field_rows[name] = rows
                    manifest["artifacts"].append(artifact)
                    manifest["artifacts"].append(check_artifact(directory/(name+'_extrema.csv'), 'csv'))
                    manifest["checks"].append({"name": name, "status": "exported", "rows": len(rows),
                                               "storage_note": "native values; zero does not prove a quantity was stored"})
                except Exception as exc:
                    manifest["checks"].append({"name": name, "status": "failed", "reason": str(exc)})
        for domain in ("solid", "shell"):
            if not all(domain+'_'+k in field_rows for k in STRESS_KEYS + ["von_mises"]):
                continue
            rows = field_rows[domain+'_stress_x']
            headers = list(stress_metrics([0]*6))
            derived = []
            max_error = 0.0
            for i, row in enumerate(rows):
                tensor = [float(field_rows[domain+'_'+k][i]['value']) for k in STRESS_KEYS]
                metrics = stress_metrics(tensor)
                native = float(field_rows[domain+'_von_mises'][i]['value'])
                error = abs(metrics['von_mises']-native)
                if error > max(1e-6, 2e-4*abs(native)):
                    raise ValueError("Native Mises mismatch in " + domain)
                max_error = max(max_error, error)
                derived.append([row['state'], row['time'], row['entity_id'], *[metrics[k] for k in headers]])
            manifest["artifacts"].append(write_csv(directory/(domain+'_invariants.csv'),
                                        ['state','time','entity_id',*headers], derived, NULLABLE))
            manifest["checks"].append({"name": domain+'_invariants', "status": "numerically_checked",
                                       "native_mises_max_absolute_error": max_error})
        for name in curves:
            try:
                rows = read_native_xy(directory / (name+'.xy'))
                manifest["artifacts"].append(write_csv(directory/(name+'.csv'), ['time','value'], rows))
                manifest["checks"].append({"name": name, "status": "exported", "rows": len(rows)})
            except Exception as exc:
                manifest["checks"].append({"name": name, "status": "failed", "reason": str(exc)})
        try:
            # Native graphics has a different startup/cwd behavior. Use the
            # verified Python bridge in a separate owned job while staging lives.
            from .service import Service
            image_job = Service(settings).render_snapshot(str(directory/'d3plot'), 'd3plot', state=states, fringe_code=9)
            manifest['image_job_id'] = image_job['job_id']
            if image_job['status'] != 'succeeded':
                raise ValueError(str(image_job.get('error')))
            shutil.copyfile(image_job['artifacts'][0]['path'], directory/'mises.png')
            manifest["artifacts"].append(check_artifact(directory/'mises.png', 'png'))
            manifest["checks"].append({"name": "mises_image", "status": "exported"})
        except Exception as exc:
            manifest["checks"].append({"name": "mises_image", "status": "failed", "reason": str(exc)})
        manifest["input_unchanged"] = original == [fingerprint(p) for p in sources + ascii_files]
        if not manifest["input_unchanged"]:
            raise ValueError("Source changed during native processing")
        manifest.update(status="partial" if any(c["status"] == "failed" for c in manifest["checks"]) else "succeeded",
                        conventions=CONVENTIONS, sampling="All saved states; first/middle/last entity per type; no spatial coverage claim",
                        ascii_present=[p.name for p in ascii_files],
                        ascii_not_exported=[p.name for p in ascii_files if p.name not in ('glstat', 'nodout', 'matsum')])
    except Exception as exc:
        manifest.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
    finally:
        # Delete only the exact source copies created above, never user originals or output evidence.
        for p in created_copies:
            if p.parent.resolve() != directory.resolve() or p.is_symlink():
                raise RuntimeError("Refuse staging cleanup outside owned job")
            p.unlink()
        manifest["staging_copies_removed"] = True
    manifest.update(finished_at=now(), job_directory=str(directory))
    atomic_json(directory/'job.json', manifest)
    return manifest
