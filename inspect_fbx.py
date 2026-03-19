import bpy
import sys

fbx_path = r"c:\Users\Krish\Downloads\MP2B 01 BETA\MP2B 01 BETA\MP2B_Extension\mp2b_extension\mp2b_extension\Dummy.fbx"
bpy.ops.import_scene.fbx(filepath=fbx_path)

for obj in bpy.context.scene.objects:
    if obj.type == 'ARMATURE':
        print(f"ARMATURE FOUND: {obj.name}")
        for bone in obj.data.bones:
            print(f"BONE: {bone.name}")

sys.exit(0)
