from __future__ import annotations

import os
import re

import bpy

from ..utils.common import has_selected_mesh_objects, parse_phrase_list, selected_mesh_objects


def _mesh_objects_with_shape_keys(context: bpy.types.Context) -> list[bpy.types.Object]:
    return [
        obj
        for obj in context.selected_objects
        if obj.type == "MESH" and obj.data.shape_keys and obj.data.shape_keys.key_blocks
    ]


def _ensure_default_shape_keys(obj: bpy.types.Object) -> None:
    required_names = ("Basis", "Width", "Height")
    if not obj.data.shape_keys:
        for name in required_names:
            obj.shape_key_add(name=name)
        return
    for name in required_names:
        if obj.data.shape_keys.key_blocks.find(name) == -1:
            obj.shape_key_add(name=name)


def _common_prefix(names: list[str]) -> str:
    if not names:
        return ""
    return os.path.commonprefix(names)


class LCW_OT_shape_key_create_default(bpy.types.Operator):
    bl_idname = "lcw.shape_key_create_default"
    bl_label = "Ensure Default Width/Height Keys"
    bl_description = "Runs on all selected mesh objects and ensures Basis, Width, and Height shape keys exist, creating any missing defaults"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        count = 0
        for obj in selected_mesh_objects(context):
            _ensure_default_shape_keys(obj)
            count += 1
        self.report({"INFO"}, f"Initialized default shape keys on {count} object(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_match_active(bpy.types.Operator):
    bl_idname = "lcw.shape_key_match_active"
    bl_label = "Sync Active Shape Key Across Selection"
    bl_description = "Uses the active object's active shape key as the source, applies the same active key to the rest of the selected objects, and deselects objects that do not contain a matching shape key"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and obj.active_shape_key)

    def execute(self, context: bpy.types.Context):
        active_obj = context.active_object
        active_key = active_obj.active_shape_key
        matched = 0
        deselected = 0
        for obj in selected_mesh_objects(context):
            if obj == active_obj:
                continue
            if obj.data.shape_keys and obj.data.shape_keys.key_blocks.find(active_key.name) != -1:
                obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find(active_key.name)
                matched += 1
            else:
                obj.select_set(False)
                deselected += 1
        self.report({"INFO"}, f"Matched {matched} object(s), deselected {deselected}.")
        return {"FINISHED"}


class LCW_OT_shape_key_set_value(bpy.types.Operator):
    bl_idname = "lcw.shape_key_set_value"
    bl_label = "Set Active Shape Key Value Across Selection"
    bl_description = "Uses the active object's active shape key as the source, copies the entered value to matching selected objects, and deselects objects that do not contain a matching shape key"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(
        name="Value",
        description="Shape key value applied to the active shape key across matching selected objects",
        default=1.0,
        min=0.0,
        max=1.0,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and obj.active_shape_key)

    def execute(self, context: bpy.types.Context):
        active_obj = context.active_object
        active_key = active_obj.active_shape_key
        updated = 0
        deselected = 0
        active_key.value = self.value
        for obj in selected_mesh_objects(context):
            if not obj.data.shape_keys:
                obj.select_set(False)
                deselected += 1
                continue
            index = obj.data.shape_keys.key_blocks.find(active_key.name)
            if index == -1:
                obj.select_set(False)
                deselected += 1
                continue
            obj.active_shape_key_index = index
            obj.data.shape_keys.key_blocks[index].value = self.value
            updated += 1
        self.report({"INFO"}, f"Updated shape key value on {updated} object(s), deselected {deselected}.")
        return {"FINISHED"}


class LCW_OT_shape_key_copy_names(bpy.types.Operator):
    bl_idname = "lcw.shape_key_copy_names"
    bl_label = "Copy Shape Key Names from Active Object"
    bl_description = "Uses the active object as the source and ensures the rest of the selected mesh objects contain the same shape key names"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return bool(obj and obj.type == "MESH" and obj.data.shape_keys)

    def execute(self, context: bpy.types.Context):
        active_obj = context.active_object
        active_names = [key.name for key in active_obj.data.shape_keys.key_blocks]
        copied = 0
        for obj in selected_mesh_objects(context):
            if obj.data.shape_keys is None:
                obj.shape_key_add(name="Basis")
            for name in active_names:
                if obj.data.shape_keys.key_blocks.find(name) == -1:
                    obj.shape_key_add(name=name)
            copied += 1
        self.report({"INFO"}, f"Copied shape key names to {copied} object(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_set_active_phrase(bpy.types.Operator):
    bl_idname = "lcw.shape_key_set_active_phrase"
    bl_label = "Select Shape Key by Name Fragment"
    bl_description = "Runs on all selected mesh objects, finds the first shape key containing the entered text, sets it active, and deselects objects without a match"
    bl_options = {"REGISTER", "UNDO"}

    phrase: bpy.props.StringProperty(
        name="Name Fragment",
        description="Text used to find the first matching shape key on each selected object",
        default="",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        phrase = self.phrase.strip()
        if not phrase:
            self.report({"WARNING"}, "Enter a phrase to match shape key names.")
            return {"CANCELLED"}

        matched = 0
        deselected = 0
        for obj in selected_mesh_objects(context):
            if obj.data.shape_keys:
                match = next((key for key in obj.data.shape_keys.key_blocks if phrase in key.name), None)
                if match:
                    obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find(match.name)
                    matched += 1
                    continue
            obj.select_set(False)
            deselected += 1
        self.report({"INFO"}, f"Matched {matched} object(s), deselected {deselected}.")
        return {"FINISHED"}


class LCW_OT_shape_key_zero_all(bpy.types.Operator):
    bl_idname = "lcw.shape_key_zero_all"
    bl_label = "Zero All Shape Key Values"
    bl_description = "Runs on all selected objects that have shape keys and sets every shape key value to 0.0"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def execute(self, context: bpy.types.Context):
        updated = 0
        for obj in _mesh_objects_with_shape_keys(context):
            for key_block in obj.data.shape_keys.key_blocks:
                key_block.value = 0.0
            updated += 1
        self.report({"INFO"}, f"Zeroed shape keys on {updated} object(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_add_prefix(bpy.types.Operator):
    bl_idname = "lcw.shape_key_add_prefix"
    bl_label = "Add Prefix to Non-Basis Shape Keys"
    bl_description = "Runs on all selected objects and adds the entered prefix to every non-Basis shape key name"
    bl_options = {"REGISTER", "UNDO"}

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="Text added to the start of each non-Basis shape key name",
        default="",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def execute(self, context: bpy.types.Context):
        if not self.prefix:
            self.report({"WARNING"}, "Prefix is empty.")
            return {"CANCELLED"}
        renamed = 0
        for obj in _mesh_objects_with_shape_keys(context):
            for key in obj.data.shape_keys.key_blocks:
                if key.name != "Basis":
                    key.name = f"{self.prefix}{key.name}"
                    renamed += 1
        self.report({"INFO"}, f"Renamed {renamed} shape key(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_replace_words(bpy.types.Operator):
    bl_idname = "lcw.shape_key_replace_words"
    bl_label = "Replace Text in Non-Basis Shape Key Names"
    bl_description = "Runs on all selected objects and replaces the search text in non-Basis shape key names"
    bl_options = {"REGISTER", "UNDO"}

    search_text: bpy.props.StringProperty(
        name="Search Text",
        description="Text to search for in non-Basis shape key names",
        default="",
    )
    replace_text: bpy.props.StringProperty(
        name="Replace With",
        description="Replacement text used when renaming matching shape key names",
        default="",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def execute(self, context: bpy.types.Context):
        if not self.search_text:
            self.report({"WARNING"}, "Search text is empty.")
            return {"CANCELLED"}
        renamed = 0
        for obj in _mesh_objects_with_shape_keys(context):
            for key in obj.data.shape_keys.key_blocks:
                if key.name != "Basis" and self.search_text in key.name:
                    key.name = key.name.replace(self.search_text, self.replace_text)
                    renamed += 1
        self.report({"INFO"}, f"Updated {renamed} shape key(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_reset_all(bpy.types.Operator):
    bl_idname = "lcw.shape_key_reset_all"
    bl_label = "Reset Shape Keys"
    bl_description = "Runs on all selected objects and rebuilds non-Basis shape keys with the same names so they return to an empty default state. This destroys the current non-Basis shape key content and requires confirmation before running"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        return context.window_manager.invoke_confirm(self, event, title="Reset Shape Keys?", confirm_text="Reset")

    def execute(self, context: bpy.types.Context):
        reset_count = 0
        for obj in _mesh_objects_with_shape_keys(context):
            shape_key_names = [key.name for key in obj.data.shape_keys.key_blocks if key.name != "Basis"]
            for key in list(obj.data.shape_keys.key_blocks)[1:]:
                obj.shape_key_remove(key)
            for name in shape_key_names:
                obj.shape_key_add(name=name)
            reset_count += 1
        self.report({"INFO"}, f"Reset shape keys on {reset_count} object(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_reset_by_phrases(bpy.types.Operator):
    bl_idname = "lcw.shape_key_reset_by_phrases"
    bl_label = "Reset Matching Shape Keys by Name"
    bl_description = "Runs on all selected objects and recreates non-Basis shape keys whose names contain one of the entered fragments"
    bl_options = {"REGISTER", "UNDO"}

    phrases: bpy.props.StringProperty(
        name="Name Fragments",
        description="Comma-separated fragments used to find shape keys that should be reset",
        default="Width,Height",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def execute(self, context: bpy.types.Context):
        phrases = parse_phrase_list(self.phrases)
        if not phrases:
            self.report({"WARNING"}, "Enter at least one phrase.")
            return {"CANCELLED"}

        reset_count = 0
        for obj in _mesh_objects_with_shape_keys(context):
            context.view_layer.objects.active = obj
            shape_key_info = [
                (index, key.name)
                for index, key in enumerate(obj.data.shape_keys.key_blocks)
                if key.name != "Basis" and any(phrase in key.name for phrase in phrases)
            ]
            if not shape_key_info:
                continue
            names = [item[1] for item in shape_key_info]
            for key in reversed(list(obj.data.shape_keys.key_blocks)):
                if key.name != "Basis" and any(phrase in key.name for phrase in phrases):
                    obj.shape_key_remove(key)
            for target_index, name in shape_key_info:
                obj.shape_key_add(name=name)
                while obj.data.shape_keys.key_blocks.find(name) > target_index:
                    obj.active_shape_key_index = obj.data.shape_keys.key_blocks.find(name)
                    bpy.ops.object.shape_key_move(type="UP")
            reset_count += len(names)
        self.report({"INFO"}, f"Reset {reset_count} matching shape key slot(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_deselect_phrase(bpy.types.Operator):
    bl_idname = "lcw.shape_key_deselect_phrase"
    bl_label = "Deselect Objects Containing Shape Key Text"
    bl_description = "Checks mesh objects in the scene and deselects those whose shape key names contain the entered text"
    bl_options = {"REGISTER", "UNDO"}

    phrase: bpy.props.StringProperty(
        name="Name Fragment",
        description="Text used to find shape key names on scene objects that should be deselected",
        default="",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        phrase = self.phrase.strip().lower()
        if not phrase:
            self.report({"WARNING"}, "Phrase is empty.")
            return {"CANCELLED"}
        deselected = 0
        for obj in context.scene.objects:
            if obj.type == "MESH" and obj.data.shape_keys:
                if any(phrase in key.name.lower() for key in obj.data.shape_keys.key_blocks):
                    obj.select_set(False)
                    deselected += 1
        self.report({"INFO"}, f"Deselected {deselected} object(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_names_check(bpy.types.Operator):
    bl_idname = "lcw.shape_key_names_check"
    bl_label = "Create Analysis Collections from Shape Key Names"
    bl_description = "Runs on selected objects with shape keys and builds helper collections from words found in their shape key names so related objects can be inspected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def execute(self, context: bpy.types.Context):
        root_name = "Shape_key_names_check"
        root = bpy.data.collections.get(root_name)
        if root is None:
            root = bpy.data.collections.new(root_name)
            context.scene.collection.children.link(root)

        linked = 0
        linked_names: dict[str, set[str]] = {}
        for obj in _mesh_objects_with_shape_keys(context):
            for key in obj.data.shape_keys.key_blocks:
                for word in set(part for part in key.name.split("_") if part):
                    child = root.children.get(word)
                    if child is None:
                        child = bpy.data.collections.new(word)
                        root.children.link(child)
                    linked_names.setdefault(word, set())
                    if obj.name not in linked_names[word] and child.objects.get(obj.name) is None:
                        child.objects.link(obj)
                        linked_names[word].add(obj.name)
                        linked += 1
        self.report({"INFO"}, f"Linked {linked} object references into shape key collections.")
        return {"FINISHED"}


class LCW_OT_shape_key_create_auto_prefix(bpy.types.Operator):
    bl_idname = "lcw.shape_key_create_auto_prefix"
    bl_label = "Create Shape Key from Common Prefix"
    bl_description = "Detects the common prefix of existing non-Basis shape keys and creates one new key with the entered suffix"
    bl_options = {"REGISTER", "UNDO"}

    suffix: bpy.props.StringProperty(
        name="Suffix",
        description="Text appended to the detected common prefix when creating a new shape key",
        default="_v2",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def execute(self, context: bpy.types.Context):
        created = 0
        for obj in _mesh_objects_with_shape_keys(context):
            existing = [key.name for key in obj.data.shape_keys.key_blocks if key.name != "Basis"]
            prefix = _common_prefix(existing)
            if prefix:
                obj.shape_key_add(name=f"{prefix}{self.suffix}")
                created += 1
        self.report({"INFO"}, f"Created {created} shape key(s).")
        return {"FINISHED"}


class LCW_OT_shape_key_animate_partial(bpy.types.Operator):
    bl_idname = "lcw.shape_key_animate_partial"
    bl_label = "Preview Shape Keys by Name Fragment"
    bl_description = "Runs on all selected objects, temporarily previews matching shape keys across the frame range without creating keyframes, then restores the original frame and values"
    bl_options = {"REGISTER"}

    partial_names: bpy.props.StringProperty(
        name="Name Fragments",
        description="Comma-separated fragments used to find shape keys that should be previewed",
        default="width,height",
    )
    start_frame: bpy.props.IntProperty(
        name="Start Frame",
        description="First frame used for the temporary shape key preview",
        default=1,
        min=0,
    )
    end_frame: bpy.props.IntProperty(
        name="End Frame",
        description="Last frame used for the temporary shape key preview",
        default=30,
        min=1,
    )
    min_value: bpy.props.FloatProperty(
        name="Min Value",
        description="Shape key value used at the start of the preview",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    max_value: bpy.props.FloatProperty(
        name="Max Value",
        description="Shape key value used at the end of the preview",
        default=1.0,
        min=0.0,
        max=1.0,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(_mesh_objects_with_shape_keys(context))

    def _tag_redraw(self, context: bpy.types.Context) -> None:
        window = getattr(context, "window", None)
        screen = window.screen if window else context.screen
        if screen is None:
            return
        for area in screen.areas:
            area.tag_redraw()

    def _restore_original_state(self, context: bpy.types.Context) -> None:
        for key_block, original_value in self._original_values:
            try:
                key_block.value = original_value
            except ReferenceError:
                continue
        context.scene.frame_set(self._original_frame)
        self._tag_redraw(context)

    def _finish_preview(self, context: bpy.types.Context, result: str) -> set[str]:
        if getattr(self, "_timer", None) is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self._restore_original_state(context)
        return {result}

    def _apply_preview_frame(self, context: bpy.types.Context, frame: int) -> None:
        frame_range = self.end_frame - self.start_frame
        factor = 0.0 if frame_range == 0 else (frame - self.start_frame) / frame_range
        value = self.min_value + (self.max_value - self.min_value) * factor
        context.scene.frame_set(frame)
        for key_block, _original_value in self._original_values:
            key_block.value = value
        self._tag_redraw(context)

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type in {"ESC", "RIGHTMOUSE"}:
            self.report({"INFO"}, "Shape key preview cancelled and original state restored.")
            return self._finish_preview(context, "CANCELLED")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._preview_frame > self.end_frame:
            self.report({"INFO"}, f"Previewed {len(self._original_values)} shape key target(s). Original state restored.")
            return self._finish_preview(context, "FINISHED")

        self._apply_preview_frame(context, self._preview_frame)
        self._preview_frame += 1
        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context):
        if self.end_frame <= self.start_frame:
            self.report({"WARNING"}, "End frame must be greater than start frame.")
            return {"CANCELLED"}

        partial_names = [name.lower() for name in parse_phrase_list(self.partial_names)]
        if not partial_names:
            self.report({"WARNING"}, "Enter at least one partial shape key name.")
            return {"CANCELLED"}

        grouped_keys: dict[str, list[bpy.types.ShapeKey]] = {name: [] for name in partial_names}
        for obj in _mesh_objects_with_shape_keys(context):
            for key in obj.data.shape_keys.key_blocks:
                for partial_name in partial_names:
                    if partial_name in key.name.lower():
                        grouped_keys[partial_name].append(key)

        total_keys = sum(len(keys) for keys in grouped_keys.values())
        if total_keys == 0:
            self.report({"WARNING"}, "No matching shape keys found in selection.")
            return {"CANCELLED"}

        unique_keys: dict[int, bpy.types.ShapeKey] = {}
        for key_blocks in grouped_keys.values():
            for key_block in key_blocks:
                unique_keys[key_block.as_pointer()] = key_block

        self._original_frame = context.scene.frame_current
        self._original_values = [(key_block, key_block.value) for key_block in unique_keys.values()]
        self._preview_frame = self.start_frame

        fps = context.scene.render.fps / context.scene.render.fps_base
        timer_interval = max(0.01, 1.0 / fps) if fps > 0 else 0.04
        self._timer = context.window_manager.event_timer_add(timer_interval, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, f"Starting preview for {len(self._original_values)} shape key target(s).")
        return {"RUNNING_MODAL"}


CLASSES = (
    LCW_OT_shape_key_create_default,
    LCW_OT_shape_key_match_active,
    LCW_OT_shape_key_set_value,
    LCW_OT_shape_key_copy_names,
    LCW_OT_shape_key_set_active_phrase,
    LCW_OT_shape_key_zero_all,
    LCW_OT_shape_key_add_prefix,
    LCW_OT_shape_key_replace_words,
    LCW_OT_shape_key_reset_all,
    LCW_OT_shape_key_reset_by_phrases,
    LCW_OT_shape_key_deselect_phrase,
    LCW_OT_shape_key_names_check,
    LCW_OT_shape_key_create_auto_prefix,
    LCW_OT_shape_key_animate_partial,
)
