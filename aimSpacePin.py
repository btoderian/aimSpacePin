## Aim Space
## MIT License
## Copyright (c) [2026] [Blaine Toderian]
## This Update: Selection-based auto-fill, reversed UI fields, and dynamic naming, offset baking.
## Use on FK controls to create a 3 point vector based ik control system for arc and spacing cleanups. 
## Place in maya scripts folder, use shelf / python command:
## def main():
##    import aimSpacePin
##    aimSpacePin.AimSpacePinTool()

import maya.cmds as cmds
import maya.mel as mel
import math

class AimSpacePinTool:
    def __init__(self):
        self.window_name = "aimSpacePin"
        self.target_field = None
        self.aim_field = None
        self.layer_name_field = None
        self.use_layer_cb = None
        
        # 1. Initialize UI
        self.create_ui()
        
        # 2. Check for active selection to auto-populate
        self.auto_populate_selection()

    def auto_populate_selection(self):
        """Plugs selection[0] into Aim and selection[1] into Target."""
        sel = cmds.ls(sl=True)
        if len(sel) >= 1:
            cmds.textField(self.aim_field, e=True, tx=sel[0])
        if len(sel) >= 2:
            cmds.textField(self.target_field, e=True, tx=sel[-1]) # Uses last if more than 2

    def get_vis_time_range(self):
        time_slider = mel.eval('$tmpVar=$gPlayBackSlider')
        if cmds.timeControl(time_slider, q=True, rv=True):
            sel_range = cmds.timeControl(time_slider, q=True, rng=True)
            return [float(sel_range.split(":")[0]), float(sel_range.split(":")[1])]
        return [cmds.playbackOptions(q=True, min=True), cmds.playbackOptions(q=True, max=True)]

    def create_pin(self, object_name, suffix="pin_", color=17):
        clean_name = object_name.replace(":", "_")
        pin_name = cmds.circle(radius=8, name=f"{suffix}{clean_name}")[0]
        grp_name = cmds.group(empty=True, name=f"{suffix}space_{clean_name}")
        cmds.parent(pin_name, grp_name)
        cmds.setAttr(f"{pin_name}.overrideEnabled", 1)
        cmds.setAttr(f"{pin_name}.overrideColor", color)
        return pin_name, grp_name

    def get_world_pos(self, obj):
        return cmds.xform(obj, q=True, ws=True, t=True)

    def check_unlocked_channels(self, obj, attr_type):
        valid = []
        for axis in ['x', 'y', 'z']:
            if not cmds.getAttr(f"{obj}.{attr_type}{axis}", lock=True):
                valid.append(axis)
        return valid

    def set_input(self, field):
        sel = cmds.ls(sl=True)
        if sel: cmds.textField(field, e=True, tx=sel[0])

    def execute_bake(self, *args):
        target_obj = cmds.textField(self.target_field, q=True, tx=True)
        aim_obj = cmds.textField(self.aim_field, q=True, tx=True)
        
        if not all([cmds.objExists(target_obj), cmds.objExists(aim_obj)]):
            cmds.error("Invalid Target or Aim object. Please verify the names in the fields.")
            return

        time_range = self.get_vis_time_range()
        
        # --- Vector Math for Stability ---
        p_aim = self.get_world_pos(aim_obj)
        p_target = self.get_world_pos(target_obj)
        
        dir_v = [p_target[0]-p_aim[0], p_target[1]-p_aim[1], p_target[2]-p_aim[2]]
        dist = math.sqrt(sum([i**2 for i in dir_v]))
        
        if dist > 0.001:
            dir_n = [i/dist for i in dir_v]
        else:
            dir_n = [1, 0, 0]
            dist = 10.0

        ref_up = [0, 1, 0] if abs(dir_n[1]) < 0.9 else [1, 0, 0]
        side_v = [
            dir_n[1]*ref_up[2] - dir_n[2]*ref_up[1],
            dir_n[2]*ref_up[0] - dir_n[0]*ref_up[2],
            dir_n[0]*ref_up[1] - dir_n[1]*ref_up[0]
        ]

        # 1. Create Pins
        target_pin, target_grp = self.create_pin(target_obj, "pin_Target_", color=17)
        aim_pin, aim_grp = self.create_pin(aim_obj, "pin_Aim_", color=6)
        up_pin, up_grp = self.create_pin(aim_obj, "pin_UpVec_", color=13)
        aim_offset_pin, aim_offset_grp = self.create_pin(aim_obj, "pin_AimOffset_", color=6)
        make_circle = [n for n in (cmds.listHistory(aim_offset_pin) or []) if cmds.nodeType(n) == 'makeNurbsCircle']
        if make_circle:
            cmds.setAttr(f"{make_circle[0]}.radius", 12)

        # 2. Position Up-Vector (1.2 magnitude for increased manual stability)
        offset_dist = dist * 1.2
        final_up_pos = [p_aim[0] + (side_v[0] * offset_dist),
                        p_aim[1] + (side_v[1] * offset_dist),
                        p_aim[2] + (side_v[2] * offset_dist)]
        cmds.xform(up_grp, ws=True, t=final_up_pos)

        # 3. Capture Motion (target, aim, up only — offset pin baked after rig is wired)
        t_temp = cmds.parentConstraint(target_obj, target_pin, mo=False)
        a_temp = cmds.parentConstraint(aim_obj, aim_pin, mo=False)
        u_temp = cmds.parentConstraint(aim_obj, up_pin, mo=True)

        bake_list = [target_pin, aim_pin, up_pin]
        cmds.bakeResults(bake_list, t=(time_range[0], time_range[1]), simulation=True,
                         sampleBy=1, minimizeRotation=True,
                         at=["tx","ty","tz","rx","ry","rz"])

        cmds.delete(t_temp, a_temp, u_temp)

        # 4. Rig Setup
        cmds.pointConstraint(aim_pin, up_grp, mo=True)
        cmds.aimConstraint(target_pin, aim_pin, mo=True, aimVector=(1,0,0),
                           upVector=(0,1,0), worldUpType="object", worldUpObject=up_pin)

        # 5. Bake pin_AimOffset in aim_pin space (captures per-frame aim_obj position)
        cmds.parent(aim_offset_grp, aim_pin)
        for attr in ['tx','ty','tz','rx','ry','rz']:
            cmds.setAttr(f"{aim_offset_grp}.{attr}", 0)
        ao_temp = cmds.parentConstraint(aim_obj, aim_offset_pin, mo=False)
        cmds.bakeResults([aim_offset_pin], t=(time_range[0], time_range[1]),
                         simulation=True, sampleBy=1, minimizeRotation=True,
                         at=["tx","ty","tz","rx","ry","rz"])
        cmds.delete(ao_temp)

        # 6. Hierarchy Organization (aim_offset lives inside aim_pin, not master_grp)
        master_grp = cmds.group(empty=True, name=f"AimPin_{aim_obj.replace(':', '_')}_RIG")
        cmds.parent(target_grp, aim_grp, up_grp, master_grp)

        # 7. Constrain Aim Object to pin_AimOffset (mo=False — offset pin was baked to match)
        use_layer = cmds.checkBox(self.use_layer_cb, q=True, v=True)
        unlocked_t = self.check_unlocked_channels(aim_obj, 't')
        unlocked_r = self.check_unlocked_channels(aim_obj, 'r')
        skip_t = [ax for ax in ['x', 'y', 'z'] if ax not in unlocked_t]
        skip_r = [ax for ax in ['x', 'y', 'z'] if ax not in unlocked_r]

        if use_layer:
            input_layer = cmds.textField(self.layer_name_field, q=True, tx=True)
            l_name = input_layer if input_layer else f"{aim_obj.replace(':', '_')}_AimPin_Layer"

            if not cmds.animLayer(l_name, q=True, exists=True):
                anim_layer = cmds.animLayer(l_name, override=True)
            else:
                anim_layer = l_name

            attrs = [f"{aim_obj}.t{ax}" for ax in unlocked_t] + [f"{aim_obj}.r{ax}" for ax in unlocked_r]
            cmds.animLayer(anim_layer, edit=True, attribute=attrs)
            cmds.parentConstraint(aim_offset_pin, aim_obj, mo=False, layer=anim_layer, st=skip_t, sr=skip_r)
        else:
            cmds.parentConstraint(aim_offset_pin, aim_obj, mo=False, st=skip_t, sr=skip_r)

        # 7. Post-execution Focus
        cmds.select(target_pin)
        cmds.headsUpMessage(f"SUCCESS: {master_grp} created. Target Pin ready for polish.", time=2)

    def create_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
        window = cmds.window(self.window_name, title="Aim Pin Tool", widthHeight=[420, 370])
        l = cmds.columnLayout(adj=True, rs=10, co=['both', 15])
        
        cmds.separator(h=15, style='none')
        cmds.text("<b>Aim Object:</b> (What is looking)", align='left', ww=True)
        r_aim = cmds.rowLayout(nc=3, adj=2)
        cmds.text("  ")
        self.aim_field = cmds.textField()
        cmds.button(label=" << ", c=lambda x: self.set_input(self.aim_field), w=40)
        cmds.setParent(l)

        cmds.text("<b>Target Object:</b> (What is being looked at)", align='left', ww=True)
        r_target = cmds.rowLayout(nc=3, adj=2)
        cmds.text("  ")
        self.target_field = cmds.textField()
        cmds.button(label=" << ", c=lambda x: self.set_input(self.target_field), w=40)
        cmds.setParent(l)
        
        cmds.separator(h=10)
        self.use_layer_cb = cmds.checkBox(label="Use Animation Layer", v=False)
        self.layer_name_field = cmds.textField(pht="Optional: Custom Layer Name")
        
        cmds.separator(h=10)
        cmds.button(label="BUILD & BAKE AIM RIG", h=50, bgc=[0.3, 0.45, 0.3], c=self.execute_bake)
        
        cmds.showWindow(window)

if __name__ == "__main__":
    AimSpacePinTool()
