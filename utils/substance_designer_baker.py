from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import bpy


__all__ = (
    "apply_profile_to_bake_state",
    "backend_string",
    "build_ao_plan",
    "build_preview_data",
    "default_workspace_root",
    "ensure_directory",
    "execute_ao_plan",
    "export_collection_for_baker",
    "find_baked_files",
    "get_baker_profile",
    "get_export_source",
    "parse_baker_info",
    "probe_baker_executable",
    "run_baker_command",
    "sanitize_filename",
    "timestamp_job_id",
    "validate_baker_setup",
    "write_json_file",
)


PROFILE_FIELD_NAMES = (
    "selection_mode",
    "excluded_material_pattern",
    "material_name_contains",
    "excluded_material_exact",
    "output_size_x",
    "output_size_y",
    "output_size_locked",
    "output_format",
    "uv_set",
    "padding_radius",
    "enable_mip_diffusion",
    "anti_aliasing",
    "average_normals",
    "use_lowdef_as_highdef",
    "projection_max_height",
    "projection_max_depth",
    "projection_normalized_distance",
    "projection_cull_backfaces",
    "projection_match_mode",
    "projection_hit_strategy",
    "skew_correction",
    "skew_map_path",
    "projection_skew_map_invert",
    "projection_offset_map_path",
    "secondary_sample_count",
    "secondary_min_distance",
    "secondary_max_distance",
    "secondary_normalized_distance",
    "secondary_spread_angle",
    "secondary_sample_distribution",
    "culling_mode",
    "secondary_mesh_match_mode",
    "normal_map_path",
    "normal_map_space",
    "normal_map_orientation",
    "attenuation",
    "enable_ground_plane",
    "ground_offset",
)


def ensure_directory(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def default_workspace_root(addon_package: str) -> Path:
    return Path(bpy.utils.extension_path_user(addon_package, create=True)) / "substance_designer_baker"


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "unnamed"


def timestamp_job_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backend_string(preferences) -> str:
    enabled: list[str] = []
    if getattr(preferences, "substance_baker_backend_sal", False):
        enabled.append("SAL")
    if getattr(preferences, "substance_baker_backend_sora", False):
        enabled.append("SoRa")
    return ",".join(enabled)


def validate_baker_setup(executable_path: str, collection: bpy.types.Collection | None, preferences=None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not executable_path.strip():
        errors.append("Substance baker executable path is empty.")
    elif not Path(bpy.path.abspath(executable_path)).is_file():
        errors.append("Substance baker executable was not found.")

    if collection is None:
        errors.append("No target collection selected.")
    else:
        mesh_count = len([obj for obj in collection.all_objects if obj.type == "MESH"])
        if mesh_count == 0:
            errors.append("Target collection does not contain any mesh objects.")
        elif mesh_count > 500:
            warnings.append("Large collection selected; preview and export may take longer.")

    if preferences is not None and not backend_string(preferences):
        errors.append("At least one Substance baker backend must be enabled.")

    return errors, warnings


def probe_baker_executable(executable_path: str) -> tuple[bool, str]:
    resolved = bpy.path.abspath(executable_path).strip()
    if not resolved:
        return False, "Substance baker executable path is empty."

    executable = Path(resolved)
    if not executable.is_file():
        return False, "Substance baker executable was not found."

    result = run_baker_command(str(executable), ["--version"])
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "Substance baker did not respond to --version."
        return False, details

    return True, result.stdout.strip() or result.stderr.strip() or executable.name


def get_baker_profile(preferences, profile_id: str):
    if not profile_id:
        return None
    for profile in getattr(preferences, "baker_profiles", ()):
        if profile.profile_id == profile_id:
            return profile
    for profile in getattr(preferences, "baker_profiles", ()):
        if profile.name == profile_id:
            return profile
    return None


def apply_profile_to_bake_state(profile, state) -> None:
    for field_name in PROFILE_FIELD_NAMES:
        setattr(state, field_name, getattr(profile, field_name))


def _is_fbx_exporter(exporter) -> bool:
    name = getattr(exporter, "name", "") or ""
    filepath = getattr(exporter, "filepath", "") or ""
    export_properties = getattr(exporter, "export_properties", None)
    identifier = ""
    if export_properties is not None:
        bl_rna = getattr(export_properties, "bl_rna", None)
        identifier = getattr(bl_rna, "identifier", "") or ""

    tokens = " ".join((name, filepath, identifier)).lower()
    return "fbx" in tokens or filepath.lower().endswith(".fbx")


def _iter_collection_exporters(collection: bpy.types.Collection | None):
    if collection is None:
        return []
    exporters = getattr(collection, "exporters", None)
    if exporters is None:
        return []
    return list(exporters)


def _extract_fbx_export_kwargs(exporter) -> dict[str, object]:
    export_properties = getattr(exporter, "export_properties", None)
    if export_properties is None:
        return {}

    operator_props = bpy.ops.export_scene.fbx.get_rna_type().properties
    supported = {prop.identifier for prop in operator_props}
    kwargs: dict[str, object] = {}
    for prop in export_properties.bl_rna.properties:
        identifier = prop.identifier
        if identifier == "rna_type" or identifier not in supported or prop.is_readonly:
            continue
        try:
            kwargs[identifier] = getattr(export_properties, identifier)
        except Exception:
            continue
    return kwargs


def get_export_source(collection: bpy.types.Collection | None, internal_export_path: str | Path) -> dict[str, object]:
    internal_export_path = Path(internal_export_path)
    for index, exporter in enumerate(_iter_collection_exporters(collection)):
        if not _is_fbx_exporter(exporter):
            continue

        raw_exporter_path = getattr(exporter, "filepath", "") or ""
        if not raw_exporter_path.strip():
            continue
        exporter_path = Path(bpy.path.abspath(raw_exporter_path)).expanduser()

        return {
            "kind": "COLLECTION_EXPORTER",
            "name": getattr(exporter, "name", "FBX"),
            "path": exporter_path,
            "label": f"Collection Exporter: {getattr(exporter, 'name', 'FBX')} -> {exporter_path}",
            "exporter_index": index,
            "exporter": exporter,
        }

    return {
        "kind": "INTERNAL_FBX",
        "name": "Internal FBX Export",
        "path": Path(internal_export_path),
        "label": f"Internal FBX Export: {internal_export_path}",
        "exporter_index": None,
        "exporter": None,
    }


def _export_with_collection_exporter(context: bpy.types.Context, collection: bpy.types.Collection, export_source: dict[str, object]) -> Path:
    export_path = Path(export_source["path"])
    export_path.parent.mkdir(parents=True, exist_ok=True)
    exporter_index = export_source["exporter_index"]

    try:
        with context.temp_override(collection=collection):
            result = bpy.ops.collection.exporter_export(index=exporter_index)
        if "FINISHED" in result:
            return export_path
    except Exception:
        pass

    exporter = export_source["exporter"]
    kwargs = _extract_fbx_export_kwargs(exporter)
    kwargs["filepath"] = str(export_path)
    kwargs["collection"] = collection.name
    kwargs["use_selection"] = False
    kwargs["use_active_collection"] = False
    kwargs["batch_mode"] = "OFF"
    bpy.ops.export_scene.fbx(**kwargs)
    return export_path


def export_collection_to_fbx(
    context: bpy.types.Context,
    collection: bpy.types.Collection,
    export_path: str | Path,
) -> Path:
    export_path = Path(export_path)
    export_path.parent.mkdir(parents=True, exist_ok=True)

    export_objects = [obj for obj in collection.all_objects if obj.type in {"MESH", "EMPTY"}]
    if not export_objects:
        raise RuntimeError("Selected collection does not contain exportable objects.")

    bpy.ops.export_scene.fbx(
        filepath=str(export_path),
        collection=collection.name,
        use_active_collection=False,
        object_types={"EMPTY", "CAMERA", "LIGHT", "ARMATURE", "MESH", "OTHER"},
        mesh_smooth_type="OFF",
        path_mode="AUTO",
        use_mesh_modifiers=True,
        add_leaf_bones=False,
        bake_anim=False,
        apply_scale_options="FBX_SCALE_UNITS",
    )
    return export_path


def export_collection_for_baker(
    context: bpy.types.Context,
    collection: bpy.types.Collection,
    internal_export_path: str | Path,
) -> dict[str, object]:
    export_source = get_export_source(collection, internal_export_path)
    if export_source["kind"] == "COLLECTION_EXPORTER":
        export_path = _export_with_collection_exporter(context, collection, export_source)
    else:
        export_path = export_collection_to_fbx(context, collection, export_source["path"])

    export_source["path"] = export_path
    export_source["label"] = (
        f"Collection Exporter: {export_source['name']} -> {export_path}"
        if export_source["kind"] == "COLLECTION_EXPORTER"
        else f"Internal FBX Export: {export_path}"
    )
    return export_source


def run_baker_command(
    executable_path: str,
    command: list[str],
    *,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    full_command = [bpy.path.abspath(executable_path)] + command
    return subprocess.run(
        full_command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _get_object_name_from_mesh_path(mesh_path: str) -> str | None:
    parts = [part for part in mesh_path.strip().split("/") if part]
    if len(parts) >= 2:
        return parts[-2]
    return None


def parse_baker_info(raw_output: str) -> list[dict[str, str]]:
    meshes: list[dict[str, str]] = []
    mesh_name: str | None = None
    mesh_path: str | None = None
    material_id: str | None = None

    for line in raw_output.splitlines():
        mesh_match = re.match(r"^\s*Mesh:\s*(.+)\s*$", line)
        if mesh_match:
            if mesh_name and mesh_path and material_id:
                meshes.append(
                    {
                        "MeshName": mesh_name,
                        "MeshPath": mesh_path,
                        "MaterialId": material_id,
                        "ObjectName": _get_object_name_from_mesh_path(mesh_path) or mesh_name,
                    }
                )
            mesh_name = mesh_match.group(1).strip()
            mesh_path = None
            material_id = None
            continue

        path_match = re.match(r"^\s*Path:\s*(/.*)\s*$", line)
        if path_match:
            mesh_path = path_match.group(1).strip()
            continue

        material_match = re.match(r"^\s*Material ID:\s*(.+)\s*$", line)
        if material_match:
            material_id = material_match.group(1).strip()

    if mesh_name and mesh_path and material_id:
        meshes.append(
            {
                "MeshName": mesh_name,
                "MeshPath": mesh_path,
                "MaterialId": material_id,
                "ObjectName": _get_object_name_from_mesh_path(mesh_path) or mesh_name,
            }
        )

    return meshes


def build_preview_data(meshes: list[dict[str, str]], state) -> dict[str, object]:
    skipped = 0
    preview_items: list[dict[str, object]] = []
    groups: list[dict[str, object]] = []
    target_meshes: list[dict[str, str]] = []

    if state.selection_mode == "ALL_EXCEPT_EXCLUDED":
        for mesh in meshes:
            include = state.excluded_material_pattern.lower() not in mesh["MaterialId"].lower()
            if include:
                target_meshes.append(mesh)
            else:
                skipped += 1
        group_map: dict[str, list[dict[str, str]]] = {}
        for mesh in target_meshes:
            group_map.setdefault(mesh["MaterialId"], []).append(mesh)
        for material_id, material_meshes in sorted(group_map.items()):
            preview_items.append(
                {
                    "label": material_id,
                    "detail": f"{len(material_meshes)} mesh(es)",
                    "item_kind": "MATERIAL",
                    "included": True,
                }
            )
            groups.append(
                {
                    "group_name": material_id,
                    "output_suffix": sanitize_filename(material_id),
                    "selected_meshes": sorted({mesh["MeshPath"] for mesh in material_meshes}),
                    "group_kind": "MATERIAL",
                }
            )
    elif state.selection_mode == "MATCHING_MATERIAL_NAME":
        for mesh in meshes:
            include = state.material_name_contains.lower() in mesh["MaterialId"].lower()
            if include:
                target_meshes.append(mesh)
            else:
                skipped += 1
        group_map: dict[str, list[dict[str, str]]] = {}
        for mesh in target_meshes:
            group_map.setdefault(mesh["MaterialId"], []).append(mesh)
        for material_id, material_meshes in sorted(group_map.items()):
            preview_items.append(
                {
                    "label": material_id,
                    "detail": f"{len(material_meshes)} mesh(es)",
                    "item_kind": "MATERIAL",
                    "included": True,
                }
            )
            groups.append(
                {
                    "group_name": material_id,
                    "output_suffix": sanitize_filename(material_id),
                    "selected_meshes": sorted({mesh["MeshPath"] for mesh in material_meshes}),
                    "group_kind": "MATERIAL",
                }
            )
    else:
        for mesh in meshes:
            include = mesh["MaterialId"] != state.excluded_material_exact
            if include:
                target_meshes.append(mesh)
            else:
                skipped += 1
        group_map: dict[str, list[dict[str, str]]] = {}
        for mesh in target_meshes:
            group_map.setdefault(mesh["ObjectName"], []).append(mesh)
        for object_name, object_meshes in sorted(group_map.items()):
            preview_items.append(
                {
                    "label": object_name,
                    "detail": f"{len(object_meshes)} mesh(es)",
                    "item_kind": "OBJECT",
                    "included": True,
                }
            )
            groups.append(
                {
                    "group_name": object_name,
                    "output_suffix": sanitize_filename(object_name),
                    "selected_meshes": sorted({mesh["MeshPath"] for mesh in object_meshes}),
                    "group_kind": "OBJECT",
                }
            )

    if not groups:
        preview_items.append(
            {
                "label": "No bake targets found",
                "detail": "Check selection mode and filter values.",
                "item_kind": "WARNING",
                "included": False,
            }
        )

    return {
        "groups": groups,
        "preview_items": preview_items,
        "target_count": len({mesh["MeshPath"] for mesh in target_meshes}),
        "group_count": len(groups),
        "skipped_count": skipped,
        "message": "Preview ready." if groups else "No bake targets found for the current selection mode.",
    }


def build_ao_plan(
    scene_name: str,
    fbx_path: str | Path,
    output_dir: str | Path,
    preferences,
    state,
    groups: list[dict[str, object]],
) -> dict[str, object]:
    common = {
        "input_scene": str(fbx_path),
        "output_dir": str(output_dir),
        "output_size": [int(state.output_size_x), int(state.output_size_y)],
        "output_format": state.output_format,
        "uv_set": state.uv_set,
        "padding_radius": state.padding_radius,
        "enable_mip_diffusion": state.enable_mip_diffusion,
        "backends": backend_string(preferences),
        "anti_aliasing": state.anti_aliasing,
        "average_normals": state.average_normals,
        "use_lowdef_as_highdef": state.use_lowdef_as_highdef,
        "texture_cache_size": preferences.substance_baker_texture_cache_size,
        "keep_meshes_in_cache": preferences.substance_baker_keep_meshes_in_cache,
        "export_source": {
            "kind": state.export_source_kind,
            "name": state.export_source_name,
            "path": state.export_source_path,
        },
        "profile_id": state.profile_id,
    }
    common_projection = {
        "high_scene_paths": state.high_scene_paths,
        "use_cage": state.use_cage,
        "cage_scene_path": state.cage_scene_path,
        "max_height": state.projection_max_height,
        "max_depth": state.projection_max_depth,
        "normalized_distance": state.projection_normalized_distance,
        "cull_backfaces": state.projection_cull_backfaces,
        "mesh_match_mode": state.projection_match_mode,
        "hit_strategy": state.projection_hit_strategy,
        "skew_correction": state.skew_correction,
        "skew_map_path": state.skew_map_path,
        "skew_map_invert": state.projection_skew_map_invert,
        "offset_map_path": state.projection_offset_map_path,
    }
    bakers = []
    for group in groups:
        bakers.append(
            {
                "Name": "ambient_occlusion",
                "Type": "AmbientOcclusion.Raytraced",
                "SceneName": scene_name,
                "GroupName": group["group_name"],
                "OutputName": f"{sanitize_filename(scene_name)}_{group['output_suffix']}",
                "SelectedMeshes": list(group["selected_meshes"]),
                "Parameters": {
                    "secondary.sample_count": state.secondary_sample_count,
                    "secondary.min_distance": state.secondary_min_distance,
                    "secondary.max_distance": state.secondary_max_distance,
                    "secondary.normalized_distance": state.secondary_normalized_distance,
                    "secondary.sample_distribution": state.secondary_sample_distribution,
                    "secondary.spread_angle": state.secondary_spread_angle,
                    "culling_mode": state.culling_mode,
                    "secondary.mesh_match_mode": state.secondary_mesh_match_mode,
                    "normal_map_path": state.normal_map_path,
                    "normal_map_space": state.normal_map_space,
                    "normal_map_orientation": state.normal_map_orientation,
                    "attenuation": state.attenuation,
                    "enable_ground_plane": state.enable_ground_plane,
                    "ground_offset": state.ground_offset,
                },
            }
        )

    return {
        "Generator": "LC Workflow helper",
        "GeneratorVersion": "0.2.2",
        "Common": common,
        "CommonProjection": common_projection,
        "Bakers": bakers,
    }


def write_json_file(path: str | Path, data: dict[str, object]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _bake_command_from_plan(plan: dict[str, object], baker_entry: dict[str, object]) -> list[str]:
    common = plan["Common"]
    projection = plan["CommonProjection"]
    parameters = baker_entry["Parameters"]
    command: list[str] = [
        baker_entry["Type"],
        "--use_lowdef_as_highdef",
        "true" if common["use_lowdef_as_highdef"] else "false",
        "--inputs",
        common["input_scene"],
        "--output_path",
        common["output_dir"],
        "--output_name",
        baker_entry["OutputName"],
        "--output_size",
        f"{common['output_size'][0]},{common['output_size'][1]}",
        "--output_format",
        common["output_format"],
        "--backends",
        common["backends"],
        "--base.uv_set",
        str(common["uv_set"]),
        "--padding_radius",
        str(common["padding_radius"]),
        "--enable_mip_diffusion",
        "true" if common["enable_mip_diffusion"] else "false",
        "--projection.sampling_rate",
        common["anti_aliasing"],
        "--projection.smooth_normals",
        "true" if common["average_normals"] else "false",
        "--projection.max_height",
        str(projection["max_height"]),
        "--projection.max_depth",
        str(projection["max_depth"]),
        "--projection.normalized_distance",
        "true" if projection["normalized_distance"] else "false",
        "--projection.cull_backfaces",
        "true" if projection["cull_backfaces"] else "false",
        "--projection.mesh_match_mode",
        projection["mesh_match_mode"],
        "--projection.hit_strategy",
        projection["hit_strategy"],
        "--skew_correction",
        "true" if projection["skew_correction"] else "false",
        "--projection.skew_map_invert",
        "true" if projection["skew_map_invert"] else "false",
        "--secondary.sample_count",
        str(parameters["secondary.sample_count"]),
        "--secondary.min_distance",
        str(parameters["secondary.min_distance"]),
        "--secondary.max_distance",
        str(parameters["secondary.max_distance"]),
        "--secondary.normalized_distance",
        "true" if parameters["secondary.normalized_distance"] else "false",
        "--secondary.sample_distribution",
        parameters["secondary.sample_distribution"],
        "--secondary.spread_angle",
        str(parameters["secondary.spread_angle"]),
        "--culling_mode",
        parameters["culling_mode"],
        "--secondary.mesh_match_mode",
        parameters["secondary.mesh_match_mode"],
        "--attenuation",
        parameters["attenuation"],
        "--enable_ground_plane",
        "true" if parameters["enable_ground_plane"] else "false",
        "--ground_offset",
        str(parameters["ground_offset"]),
    ]

    if common["keep_meshes_in_cache"]:
        command.extend(["--keep_meshes_in_cache", "true"])
    if common["texture_cache_size"] > 0:
        command.extend(["--texture_cache_size", str(common["texture_cache_size"])])
    if projection["skew_map_path"]:
        command.extend(["--projection.skew_map_path", projection["skew_map_path"]])
    if projection["offset_map_path"]:
        command.extend(["--projection.offset_map_path", projection["offset_map_path"]])
    if parameters["normal_map_path"]:
        command.extend(["--normal_map_path", parameters["normal_map_path"]])
        command.extend(["--normal_map_space", parameters["normal_map_space"]])
        command.extend(["--normal_map_orientation", parameters["normal_map_orientation"]])

    for mesh_path in baker_entry["SelectedMeshes"]:
        command.extend(["--selected_meshes", mesh_path])

    return command


def execute_ao_plan(plan: dict[str, object], executable_path: str, log_path: str | Path) -> dict[str, object]:
    log_lines: list[str] = []
    output_dir = Path(plan["Common"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    baked_files: list[str] = []
    success = True
    failure_message = ""

    for baker_entry in plan["Bakers"]:
        command = _bake_command_from_plan(plan, baker_entry)
        log_lines.append(f"$ {Path(executable_path).name} {' '.join(command)}")
        result = run_baker_command(executable_path, command)
        if result.stdout:
            log_lines.append(result.stdout.rstrip())
        if result.stderr:
            log_lines.append(result.stderr.rstrip())
        if result.returncode != 0:
            success = False
            failure_message = f"Bake failed for group '{baker_entry['GroupName']}'."
            break
        baked_files.extend(find_baked_files(output_dir, baker_entry["OutputName"]))

    Path(log_path).write_text("\n\n".join(part for part in log_lines if part), encoding="utf-8")
    return {
        "success": success,
        "message": "AO bake completed successfully." if success else failure_message or "AO bake failed.",
        "baked_files": baked_files,
        "log_path": str(log_path),
        "output_dir": str(output_dir),
    }


def find_baked_files(output_dir: str | Path, output_name: str) -> list[str]:
    output_dir = Path(output_dir)
    return sorted(str(path) for path in output_dir.glob(f"{output_name}*") if path.is_file())


def cleanup_path(path: str | Path) -> None:
    target = Path(path)
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.exists():
        target.unlink(missing_ok=True)
