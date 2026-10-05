"""Render named native fields from the same arrays exported as numeric evidence."""

import csv
import json
import math
from contextlib import nullcontext

from .config import command_path, scl_command_path
from .core.native_log import native_errors, read_delta
from .field_contracts import FieldSpec, ResultSelection, SamplingSpec
from .fringe_presentation import averaging_command, result_name
from .gui_controls import wait_for_gui_state
from .gui_curves import plot_text
from .jobs import atomic_json, check_artifact, now
from .native import commands as nc
from .native_results import ELEMENT_FIELDS, NODE_FIELDS
from .post_backend import ids, write_csv
from .result_availability import validate_field_availability
from .result_validity import validity_scope
from .scene_state import fringe_coverage

KINDS = {"beam": 1, "shell": 2, "solid": 3, "tshell": 4}
LIMIT = 1000000
RENDER_ELEMENT_FIELDS = ELEMENT_FIELDS | {"mean_stress", "pressure"}


def scl_string(path):
    return json.dumps(str(path).replace("\\", "/"), ensure_ascii=False)


def context_script(parts, path):
    rows = "\n".join(
        'fprintf(fp,"%d,%%d,%%d,%%d\\n",SCLInquiryPartTypeU(%d),SCLCheckIfPartIsActiveU(%d),SCLGetDataCenterInt("is_full_integrated"));'
        % (uid, uid, uid)
        for uid in parts
    )
    return (
        "/*LS-SCRIPT*/\ndefine:\nvoid main(void){\nFILE *fp;\nfp=fopen("
        + scl_string(path)
        + ',"w");\nif(fp==NULL)return;\nfprintf(fp,"part_id,type,visible,full_integrated\\n");\n'
        + rows
        + "\nfclose(fp);\n}\nmain();\n"
    )


def field_fringe_script(domain, field, state, time_value, ipt, selected_parts, path, label, marker, physical_mask=False):
    kind = domain.upper()
    counter = "num_nodes" if domain == "node" else "num_" + domain + "_elements"
    select = " || ".join("pid==%d" % pid for pid in selected_parts)
    loads = 'k=SCLGetDataCenterFloatArray("%s",%s,%s,&v);\nif(k!=n)ok=0;\n' % (field, kind, ipt)
    if field == "disp_magnitude":
        loads = "\n".join(
            'k=SCLGetDataCenterFloatArray("disp_%s",NODE,0,&%s);\nif(k!=n)ok=0;' % (axis, name)
            for axis, name in zip("xyz", ("v", "v1", "v2"))
        )
        loads += "\nif(ok)for(j=0;j<n;j=j+1)v[j]=sqrt(v[j]*v[j]+v1[j]*v1[j]+v2[j]*v2[j]);\n"
    elif field in ("mean_stress", "pressure"):
        loads = "\n".join(
            'k=SCLGetDataCenterFloatArray("stress_%s",%s,%s,&%s);\nif(k!=n)ok=0;' % (axis, kind, ipt, name)
            for axis, name in zip("xyz", ("v", "v1", "v2"))
        )
        sign = "-" if field == "pressure" else ""
        loads += f"\nif(ok)for(j=0;j<n;j=j+1)v[j]={sign}(v[j]/3.0+v1[j]/3.0+v2[j]/3.0);\n"
    if domain == "node":
        # Use actual user connectivity and native visibility, never nearest-node or index guesses.
        selection = "\n".join(
            """
pid=%d;
tp=SCLInquiryPartTypeU(pid);
k=SCLGetDataCenterIntArray("elemofpart_ids",&eids,1,pid);
if(k<0 || k>ne)ok=0;
if(ok)for(i=0;i<k;i=i+1){
 ei=SCLGetInternalID(eids[i],tp);
 if(ei<0){ok=0;break;}
 if(SCLCheckIfElementisActiveI(ei,tp)){
  nc=SCLGetDataCenterIntArray("element_connectivity",&conn,tp,eids[i]);
  if(nc<1 || nc>32){ok=0;break;}
  for(c=0;c<nc;c=c+1){
   if(conn[c]>0){ni=SCLGetInternalID(conn[c],NODE);if(ni<0 || ni>=n)ok=0;else mask[ni]=1;}
  }
 }
}
"""
            % pid
            for pid in selected_parts
        )
        emit = (
            'if(mask[j]){fprintf(fp,"%d,%.17g,%%d,,%%.17g\\n",SCLGetUserId(j,NODE),v[j]);written=written+1;}'
            % (state, time_value)
        )
    else:
        selection = (
            "for(j=0;j<n;j=j+1){uid=SCLGetUserId(j,%s);pid=SCLGetUserPartIDFromUserElementID(uid,%s);if((%s) && SCLCheckIfElementisActiveI(j,%s))mask[j]=1;}\n"
            % (kind, kind, select, kind)
        )
        emit = (
            'if(mask[j]){uid=SCLGetUserId(j,%s);pid=SCLGetUserPartIDFromUserElementID(uid,%s);fprintf(fp,"%d,%.17g,%%d,%%d,%%.17g\\n",uid,pid,v[j]);written=written+1;}'
            % (kind, kind, state, time_value)
        )
    return (
        """/*LS-SCRIPT*/
define:
void main(void){
Int n,ne,k,j,i,c,nc,tp,uid,pid,ei,ni,ok=1,written=0;
Int *mask=NULL,*eids=NULL,*conn=NULL;
Float *v=NULL,*v1=NULL,*v2=NULL;
FILE *fp;
"""
        + f'n=SCLGetDataCenterInt("{counter}");\nne=SCLGetDataCenterInt("num_elements");\nif(n<1 || n>{LIMIT} || ne<1 || ne>{LIMIT} || SCLGetDataCenterInt("current_state")!={state})return;\n'
        + """
v=malloc(n*sizeof(Float));v1=malloc(n*sizeof(Float));v2=malloc(n*sizeof(Float));
mask=malloc(n*sizeof(Int));eids=malloc(ne*sizeof(Int));conn=malloc(32*sizeof(Int));
for(j=0;j<n;j=j+1)mask[j]=0;
"""
        + "SCLSwitchStateTo(%d);\n" % state
        + loads
        + "\nif(ok){\n"
        + selection
        + ("\n}\nif(ok){\nfor(j=0;j<n;j=j+1){if(mask[j]){if(v[j]!=v[j] || v[j]>3e38 || v[j]<-3e38)ok=0;}else v[j]=0;}\n}\nif(ok){\nfp=fopen("
           if physical_mask else
           "\n}\nif(ok){\nfor(j=0;j<n;j=j+1)if(v[j]!=v[j] || v[j]>3e38 || v[j]<-3e38)ok=0;\n}\nif(ok){\nfp=fopen(")
        + scl_string(path)
        + ',"w");\nif(fp!=NULL){\nfprintf(fp,"state,time,entity_id,part_id,'
        + field
        + '\\n");\nfor(j=0;j<n;j=j+1){'
        + emit
        + "}\nfclose(fp);\nif(written>0){\n"
        + "SCLFringeDCToModel(%s,0,n,v,%d,%s);\n" % (kind, state, json.dumps(label))
        + "fp=fopen("
        + scl_string(marker)
        + ',"w");\nif(fp!=NULL){fprintf(fp,"%d %d\\n",n,written);fclose(fp);}\n}\n}\n}\nfree(v);free(v1);free(v2);free(mask);free(eids);free(conn);\n}\nmain();\n'
    )


def parse_field(path, marker, domain, field, state, time_value, selected_parts):
    numbers = [int(v) for v in marker.read_text().split()]
    if len(numbers) != 2 or not 1 <= numbers[1] <= numbers[0] <= LIMIT:
        raise ValueError("Native field completion counts are invalid")
    rows, seen = [], set()
    with path.open(encoding="utf8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["state", "time", "entity_id", "part_id", field]:
            raise ValueError("Native field column contract mismatch")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed native field row")
            uid = int(row["entity_id"])
            pid = int(row["part_id"]) if row["part_id"] else None
            value = float(row[field])
            if (
                type(uid) is not int
                or not 1 <= uid <= 2000000000
                or uid in seen
                or not math.isfinite(value)
                or int(row["state"]) != state
                or float(row["time"]) != time_value
                or (domain == "node" and pid is not None)
                or (domain != "node" and pid not in selected_parts)
            ):
                raise ValueError("Native field IDs/state/part/value do not match the render request")
            seen.add(uid)
            rows.append([state, time_value, uid, pid, value])
            if len(rows) > numbers[1]:
                raise ValueError("Native field has extra rows")
    if len(rows) != numbers[1]:
        raise ValueError("Native field output is incomplete")
    return rows, numbers[0]


def field_range(values, requested):
    lower, upper = min(values), max(values)
    if requested is None:
        if lower == upper:
            padding = abs(lower) * 1e-6 if lower else 1e-6
            return [lower - padding, upper + padding]
        return [lower, upper]
    if (
        not isinstance(requested, list)
        or len(requested) != 2
        or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 3e38 for v in requested)
        or requested[0] >= requested[1]
    ):
        raise ValueError("color_range requires two ordered finite native-scale numbers")
    return list(requested)


def render_field(
    service, session_id, entity_type, field, state, units, integration_point, part_ids, color_range, averaging="minmax",
    validity_policy="raw", *, _locked=False, _journal=True
):
    validity_scope(validity_policy)
    if validity_policy == "alive" and entity_type not in ("solid", "shell"):
        raise ValueError("Physical fringe masking currently supports standard solid/shell elements")
    average_command = averaging_command(averaging)
    if entity_type not in ("node", "solid", "shell", "tshell") or field not in (
        NODE_FIELDS if entity_type == "node" else RENDER_ELEMENT_FIELDS
    ):
        raise ValueError("Unsupported named native render field/domain")
    if type(state) is not int or state < 1:
        raise ValueError("state must be a positive 1-based integer")
    plot_text(units, "units", 20)
    sampling = SamplingSpec.native_fields(entity_type, integration_point, [field])
    if part_ids is not None:
        ids(part_ids, "part_ids", 5000)
        if len(set(part_ids)) != len(part_ids):
            raise ValueError("Duplicate part IDs")
    if color_range is not None:
        field_range([0], color_range)
    manager = service._session_manager()
    with nullcontext() if _locked else manager.lock(session_id):
        meta = service._visible_mesh_session(session_id, manager, allow_results=True)
        if meta["model_kind"] != "d3plot":
            raise ValueError("Field rendering requires a result session")
        observed = manager.dispatch(session_id, "inspect_model", {"include_display_scope": True})
        if observed["status"] != "succeeded":
            return observed
        before = observed["data"]
        if "part_visibility" not in before or "selection_count" not in before:
            raise ValueError("Start a new GUI session to use the updated display-scope bridge")
        if state > len(before.get("state_times", [])) or not math.isfinite(before["state_times"][state - 1]):
            raise ValueError("Native result timeline is unavailable or nonfinite")
        ids(before["part_ids"], "native_part_ids", 5000)
        availability = validate_field_availability(
            service.settings, meta.get("staged_model"), before["counts"], entity_type, field, sampling
        )
        if (
            state > before["counts"]["states"]
            or max(before["counts"]["nodes"], before["counts"]["elements"]) > LIMIT
            or len(before["part_ids"]) > 5000
        ):
            raise ValueError("Result state or model exceeds the native field resource scope")
        parameters = dict(
            entity_type=entity_type,
            field=field,
            state=state,
            units=units,
            integration_point=integration_point,
            part_ids=part_ids,
            color_range=color_range,
            averaging=averaging,
            validity_policy=validity_policy,
        )
        directory, manifest = service.jobs.create(
            "render_gui_field", dict(session_id=session_id, **parameters)
        )
        manifest.update(
            status="running",
            session_id=session_id,
            process=meta["process"],
            started_at=now(),
            job_directory=str(directory),
            backend="lsprepost",
            native_channel="scl_custom_fringe",
        )
        atomic_json(directory / "before.json", before)
        log = manager.directory(session_id) / "lspost.msg"
        offset = log.stat().st_size if log.exists() else 0

        def diagnostics():
            if not log.exists():
                return []
            content = read_delta(log, offset, existed=True)
            (directory / "native.log").write_text(content, encoding="utf8")
            return native_errors(content)

        try:
            context = directory / "context.scl"
            context.write_text(context_script(before["part_ids"], directory / "parts.csv"), encoding="utf8")
            info = manager.dispatch(
                session_id, "inspect_model", {}, native_commands=["runscript " + scl_command_path(context)]
            )
            if info["status"] != "succeeded":
                raise ValueError("Cannot inspect native part domains")
            if diagnostics():
                raise ValueError("Native context script diagnostics: " + "; ".join(diagnostics()))
            with (directory / "parts.csv").open(newline="") as stream:
                parts = list(csv.DictReader(stream))
            if len(parts) != len(before["part_ids"]) or {int(r["part_id"]) for r in parts} != set(
                before["part_ids"]
            ):
                raise ValueError("Native part registry mismatch")
            if any(int(r["visible"]) not in (0, 1) for r in parts):
                raise ValueError("Native part flags are not binary")
            types = {int(r["part_id"]): int(r["type"]) for r in parts}
            if (
                entity_type == "solid"
                and sampling.kind == "native_integration_point"
                and any(int(r["full_integrated"]) != 1 for r in parts)
            ):
                raise ValueError(
                    "This native database does not expose fully-integrated solid points; use the explicit native default (mid) instead"
                )
            supported = set(KINDS.values()) if entity_type == "node" else {KINDS[entity_type]}
            chosen = (
                part_ids if part_ids is not None else [pid for pid, tp in types.items() if tp in supported]
            )
            if (
                not chosen
                or not set(chosen) <= set(types)
                or any(types[pid] not in supported for pid in chosen)
            ):
                raise ValueError("Parts do not match the requested standard field domain")
            if entity_type == "node" and part_ids is None and len(chosen) != len(types):
                raise ValueError(
                    "Whole-model node fringe contains unsupported part types; choose supported parts explicitly"
                )
            definition = dict(
                domain=entity_type,
                field=field,
                units=units,
                sampling=sampling.describe(),
                parts=sorted(chosen),
                averaging=averaging,
                validity_policy=validity_policy,
            )
            previous = meta.get("managed_fringe")
            storage = {key: set(value) for key, value in meta.get("fringe_storage", {}).items()}
            storage.setdefault(entity_type, set()).add(state)
            if (
                sum(
                    before["counts"]["nodes" if key == "node" else "elements"] * len(value)
                    for key, value in storage.items()
                )
                > LIMIT
            ):
                raise ValueError(
                    "Retained custom-fringe buffers exceed one million scalar samples; reopen the model or reduce the sequence"
                )
            pending = manager.read(session_id)
            pending["managed_fringe"] = dict(status="uncertain", definition=definition, frames={})
            pending["fringe_storage"] = {key: sorted(value) for key, value in storage.items()}
            manager.save(session_id, pending)
            selected = manager.dispatch(session_id, "gui_parts", dict(mode="isolate", part_ids=chosen))
            if selected["status"] != "succeeded":
                raise ValueError("Cannot establish requested display parts")
            ready, evidence = wait_for_gui_state(
                manager,
                session_id,
                state,
                service.settings.timeout,
                native_commands=[nc.animation('stop'), nc.state(state)],
            )
            if ready["status"] != "succeeded":
                raise ValueError("Result state did not settle before field extraction")
            time_value = before["state_times"][state - 1]
            physical_report, physical_ids = None, None
            if validity_policy == "alive":
                from .gui_result_validity import physical_fringe_scope

                physical_report, physical_ids = physical_fringe_scope(
                    service, manager, session_id, meta, entity_type, state, time_value, directory
                )
            label = result_name(field)
            script = directory / "field.scl"
            script.write_text(
                field_fringe_script(
                    entity_type,
                    field,
                    state,
                    time_value,
                    sampling.native_selector,
                    chosen,
                    directory / "native.csv",
                    label,
                    directory / "complete.txt",
                    physical_mask=physical_report is not None,
                ),
                encoding="utf8",
            )
            applied = manager.dispatch(
                session_id,
                "inspect_model",
                {},
                native_commands=[nc.selection('clear'), "runscript " + scl_command_path(script)],
            )
            manifest["native_request"] = {k: v for k, v in applied.items() if k != "data"}
            if applied["status"] != "succeeded" or applied["data"]["current_state"] != state:
                raise ValueError("Native field application failed")
            if diagnostics():
                raise ValueError("Native field script diagnostics: " + "; ".join(diagnostics()))
            rows, total = parse_field(
                directory / "native.csv",
                directory / "complete.txt",
                entity_type,
                field,
                state,
                time_value,
                chosen,
            )
            bounds = field_range([r[-1] for r in rows], color_range)
            if physical_ids is not None and {r[2] for r in rows} != physical_ids:
                raise ValueError("Native fringe CSV does not match the verified visible physical population")
            commands = [
                average_command,
                nc.reverse_signs(False),
                nc.fringe_bounds(bounds[0], bounds[1]),
                "showlegend 1",
                "timestamp 1",
                "print png " + command_path(directory / "fringe.png") + ' opaque enlisted "OGL1x1"',
            ]
            captured = manager.dispatch(session_id, "inspect_model", {}, native_commands=commands)
            atomic_json(directory / "render-commands.json", commands)
            if (
                captured["status"] != "succeeded"
                or captured["data"]["current_state"] != state
                or captured["data"]["counts"] != before["counts"]
            ):
                raise ValueError("Native capture model/state mismatch")
            text = read_delta(log, offset, existed=True)
            (directory / "native.log").write_text(text, encoding="utf8")
            if native_errors(text):
                raise ValueError("Native field diagnostics reported errors")
            spec = FieldSpec(
                "lsprepost",
                (field,),
                units,
                ResultSelection(entity_type, [r[2] for r in rows], [state]),
                sampling,
                "native DataCenter component frame; no transformation",
                "Raw SCL entity values (avg_opt=0 buffer); display averaging="+averaging,
                validity_scope(validity_policy) if physical_report else
                "native display-active elements (or connected nodes); not a physical alive/deletion classification",
                ("SCL magnitude from native disp_x/y/z",)
                if field == "disp_magnitude"
                else ("SCL mean of native normal stresses; tension positive",)
                if field == "mean_stress"
                else ("SCL negative mean of native normal stresses; pressure compression positive",)
                if field == "pressure"
                else (),
            )
            described = spec.describe()
            described["selection"]["full_request_location"] = (
                "field.csv:entity_id column (expanded render selection)"
            )
            provenance = dict(
                variable_availability=availability,
                validity_policy=validity_policy,
                physical_deletion_filter_applied=physical_report is not None,
                validity=physical_report,
                field_spec=described,
                display_part_ids=chosen,
                color_range=bounds,
                color_range_policy="explicit"
                if color_range is not None
                else "exported-data min/max with padding for constant fields",
                entity_population=total,
                rendered_entity_count=len(rows),
                value_min=min(r[-1] for r in rows),
                value_max=max(r[-1] for r in rows),
                averaging_option=0,
                display_averaging=averaging,
                csv_averaging="none: raw native entity values, distinct from display averaging",
                title_policy="Preserve model title; native result name without automatic suffixes",
                state=state,
                time=time_value,
                legend_label=label,
                scene_after="requested state/parts/custom fringe retained; animation stopped; general selection cleared to avoid overlays",
            )
            atomic_json(directory / "field-spec.json", provenance)
            manifest.update(
                status="succeeded",
                data=provenance,
                artifacts=[
                    check_artifact(directory / "fringe.png", "png"),
                    write_csv(
                        directory / "field.csv",
                        ["state", "time", "entity_id", "part_id", field],
                        rows,
                        ("part_id",),
                    ),
                    check_artifact(directory / "field-spec.json", "json"),
                ],
            )
            current = manager.read(session_id)
            current["managed_fringe"] = fringe_coverage(previous, definition, state, str(directory))
            current["managed_fringe"]["color_range"] = bounds
            manager.save(session_id, current)
        except Exception as exc:
            manifest.update(
                status="failed",
                error=dict(type=type(exc).__name__, message=str(exc)),
                warnings=[
                    "Partial display changes may remain; source files are not modified and no automatic replay occurs"
                ],
            )
            manifest["native_diagnostics"] = diagnostics()
        manifest["finished_at"] = now()
        atomic_json(directory / "job.json", manifest)
        if _journal:
            manager.journal(session_id, dict(action="render_gui_field", parameters=parameters, result=manifest))
        return manifest
