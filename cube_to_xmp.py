import os
import struct
import zlib
import base64
import uuid

def parse_cube(filepath):
    size = 33
    data = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("TITLE") or line.startswith("DOMAIN"):
                continue
            if line.startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
                continue
            parts = line.split()
            if len(parts) == 3:
                data.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return size, data

def encode_adobe_lut_table(size, rgb_data):
    """Packs 3D LUT into Adobe Camera Raw / Lightroom Mobile binary Table format."""
    raw = bytearray()
    # Header: 4 x int32 (version=1, count=3,gridPoints=size, extra=1)
    raw.extend(struct.pack("<IIII", 1, 3, size, 1))
    for r, g, b in rgb_data:
        u_r = int(min(max(r, 0.0), 1.0) * 65535.0 + 0.5)
        u_g = int(min(max(g, 0.0), 1.0) * 65535.0 + 0.5)
        u_b = int(min(max(b, 0.0), 1.0) * 65535.0 + 0.5)
        raw.extend(struct.pack("<HHH", u_r, u_g, u_b))
    # Footer: min/max float range
    raw.extend(struct.pack("<dddddd", 0.0, 0.0, 0.0, 1.0, 1.0, 1.0))
    
    compressed = zlib.compress(bytes(raw), level=9)
    # Adobe prefixes compressed block with uncompressed byte length (uint32 little-endian)
    packed = struct.pack("<I", len(raw)) + compressed
    # Base85 / ASCII85 style or standard XMP Table hex-hash
    table_id = uuid.uuid4().hex.upper()
    return table_id, base64.b64encode(packed).decode("ascii")

def create_lightroom_xmp(name, cube_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    # Standard XMP wrapper for quick import in Lightroom Mobile
    uid = uuid.uuid4().hex.upper()
    clean_name = name.replace("_", " ")
    
    xmp_content = f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:PresetType="Normal"
    crs:Cluster=""
    crs:UUID="{uid}"
    crs:SupportsAmount="True"
    crs:SupportsColor="True"
    crs:SupportsMonochrome="True"
    crs:SupportsHighDynamicRange="True"
    crs:SupportsNormalDynamicRange="True"
    crs:SupportsSceneReferred="True"
    crs:SupportsOutputReferred="True"
    crs:CameraModelRestriction=""
    crs:Copyright=""
    crs:ContactInfo=""
    crs:Version="15.0"
    crs:ProcessVersion="11.0"
    crs:HasSettings="True">
   <crs:Name>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{clean_name}</rdf:li>
    </rdf:Alt>
   </crs:Name>
   <crs:Group>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">iOS Photos Native</rdf:li>
    </rdf:Alt>
   </crs:Group>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""
    with open(os.path.join(out_dir, f"{name}.xmp"), "w") as f:
        f.write(xmp_content)

if __name__ == "__main__":
    os.makedirs("output_xmp", exist_ok=True)
    for fname in sorted(os.listdir("output_cubes")):
        if fname.endswith(".cube"):
            name = fname[:-5]
            create_lightroom_xmp(name, os.path.join("output_cubes", fname), "output_xmp")
            print(f"Prepared {name}")
