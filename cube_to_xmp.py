import os
import struct
import zlib
import hashlib
import uuid

# Adobe Camera Raw / DNG SDK custom XML-safe ASCII85 alphabet
ADOBE_85 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?`'|()[]{}@%$#"

def encode_adobe_ascii85(data: bytes) -> str:
    """Encodes bytes using Adobe Camera Raw's little-endian Base85 format."""
    out = []
    n = len(data)
    i = 0
    # Process full 4-byte little-endian uint32 blocks -> 5 chars
    while i + 4 <= n:
        val = struct.unpack_from("<I", data, i)[0]
        for _ in range(5):
            out.append(ADOBE_85[val % 85])
            val //= 85
        i += 4

    # Process remaining 1 to 3 tail bytes -> len(rem) + 1 chars
    rem = n - i
    if rem > 0:
        tail = data[i:] + b"\x00" * (4 - rem)
        val = struct.unpack("<I", tail)[0]
        for _ in range(rem + 1):
            out.append(ADOBE_85[val % 85])
            val //= 85

    return "".join(out)

def parse_cube(filepath: str):
    size = 33
    rgb_list = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("TITLE") or line.startswith("DOMAIN"):
                continue
            if line.startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
                continue
            parts = line.split()
            if len(parts) == 3:
                rgb_list.append((float(parts[0]), float(parts[1]), float(parts[2])))
    return size, rgb_list

def build_crs_rgb_table(size: int, rgb_data: list):
    """
    Builds the exact binary payload expected by Lightroom's crs:Table_<ID> attribute.
    Note: .cube files order Red fastest, Green middle, Blue slowest.
    Adobe's binary table orders Blue fastest (inner loop), Green middle, Red slowest (outer loop),
    and stores uint16 modulo-65536 deltas from the identity grid.
    """
    raw = bytearray()
    # 16-byte header: version=1, type=1, dimensions=3, divisions=size
    raw.extend(struct.pack("<IIII", 1, 1, 3, size))

    # Convert .cube list (indexed by b * size^2 + g * size + r) into Adobe loop order (r, g, b)
    scale = 65535.0 / (size - 1)
    for r_idx in range(size):
        id_r = int(round(r_idx * scale))
        for g_idx in range(size):
            id_g = int(round(g_idx * scale))
            for b_idx in range(size):
                id_b = int(round(b_idx * scale))
                
                cube_idx = b_idx * (size * size) + g_idx * size + r_idx
                rf, gf, bf = rgb_data[cube_idx]
                
                val_r = int(min(max(rf, 0.0), 1.0) * 65535.0 + 0.5)
                val_g = int(min(max(gf, 0.0), 1.0) * 65535.0 + 0.5)
                val_b = int(min(max(bf, 0.0), 1.0) * 65535.0 + 0.5)

                # Delta from identity wrapped to uint16
                d_r = (val_r - id_r) & 0xFFFF
                d_g = (val_g - id_g) & 0xFFFF
                d_b = (val_b - id_b) & 0xFFFF

                raw.extend(struct.pack("<HHH", d_r, d_g, d_b))

    # 56-byte footer: ColorSpace (1=sRGB, 0=ProPhoto), Gamut (0=unclipped), 6 doubles (min/max bounds)
    raw.extend(struct.pack("<IIdddddd", 1, 0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0))

    raw_bytes = bytes(raw)
    table_hash = hashlib.md5(raw_bytes).hexdigest().upper()

    compressed = zlib.compress(raw_bytes, level=9)
    packed = struct.pack("<I", len(raw_bytes)) + compressed
    encoded_str = encode_adobe_ascii85(packed)

    return table_hash, encoded_str

def generate_xmp_files(name: str, cube_path: str, profile_dir: str, preset_dir: str):
    size, rgb_data = parse_cube(cube_path)
    table_id, encoded_table = build_crs_rgb_table(size, rgb_data)

    clean_name = name.replace("_", " ")
    profile_uuid = hashlib.md5(f"profile_{name}".encode()).hexdigest().upper()
    preset_uuid = hashlib.md5(f"preset_{name}".encode()).hexdigest().upper()

    # 1. Creative Profile XMP (Appears in Profiles tab with 0-200% slider)
    profile_xmp = f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:PresetType="Look"
    crs:Cluster=""
    crs:UUID="{profile_uuid}"
    crs:SupportsAmount="True"
    crs:SupportsColor="True"
    crs:SupportsMonochrome="True"
    crs:SupportsHighDynamicRange="True"
    crs:SupportsNormalDynamicRange="True"
    crs:SupportsSceneReferred="True"
    crs:SupportsOutputReferred="True"
    crs:Copyright="Apple CoreImage Extracted"
    crs:Version="15.4"
    crs:ProcessVersion="11.0"
    crs:ConvertToGrayscale="False"
    crs:RGBTable="{table_id}"
    crs:Table_{table_id}="{encoded_table}"
    crs:HasSettings="True">
   <crs:Name>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{clean_name}</rdf:li>
    </rdf:Alt>
   </crs:Name>
   <crs:ShortName>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{clean_name}</rdf:li>
    </rdf:Alt>
   </crs:ShortName>
   <crs:SortName>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{clean_name}</rdf:li>
    </rdf:Alt>
   </crs:SortName>
   <crs:Group>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">iOS Photos Native</rdf:li>
    </rdf:Alt>
   </crs:Group>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""

    # 2. One-Tap Preset XMP (Appears in Presets tab with embedded Look table)
    preset_xmp = f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:PresetType="Normal"
    crs:Cluster=""
    crs:UUID="{preset_uuid}"
    crs:SupportsAmount2="True"
    crs:SupportsAmount="True"
    crs:SupportsColor="True"
    crs:SupportsMonochrome="True"
    crs:SupportsHighDynamicRange="True"
    crs:SupportsNormalDynamicRange="True"
    crs:SupportsSceneReferred="True"
    crs:SupportsOutputReferred="True"
    crs:Version="15.4"
    crs:ProcessVersion="11.0"
    crs:HasSettings="True">
   <crs:Name>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{clean_name}</rdf:li>
    </rdf:Alt>
   </crs:Name>
   <crs:Group>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">iOS Photos Presets</rdf:li>
    </rdf:Alt>
   </crs:Group>
   <crs:Look>
    <rdf:Description
      crs:Name="{clean_name}"
      crs:Amount="1"
      crs:Cluster=""
      crs:UUID="{profile_uuid}"
      crs:SupportsAmount="false"
      crs:SupportsMonochrome="false"
      crs:SupportsOutputReferred="false"
      crs:Stubbed="true">
     <crs:Group>
      <rdf:Alt>
       <rdf:li xml:lang="x-default">iOS Photos Native</rdf:li>
      </rdf:Alt>
     </crs:Group>
     <crs:Parameters>
      <rdf:Description
        crs:Version="15.4"
        crs:ProcessVersion="11.0"
        crs:ConvertToGrayscale="False"
        crs:RGBTable="{table_id}"
        crs:Table_{table_id}="{encoded_table}"/>
     </crs:Parameters>
    </rdf:Description>
   </crs:Look>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""

    os.makedirs(profile_dir, exist_ok=True)
    os.makedirs(preset_dir, exist_ok=True)

    with open(os.path.join(profile_dir, f"{name}_Profile.xmp"), "w", encoding="utf-8") as f:
        f.write(profile_xmp)
    with open(os.path.join(preset_dir, f"{name}_Preset.xmp"), "w", encoding="utf-8") as f:
        f.write(preset_xmp)

if __name__ == "__main__":
    cube_dir = "output_cubes"
    for fname in sorted(os.listdir(cube_dir)):
        if fname.endswith(".cube"):
            filter_name = fname[:-5]
            generate_xmp_files(
                filter_name,
                os.path.join(cube_dir, fname),
                "output_xmp_profiles",
                "output_xmp_presets"
            )
            print(f"Packed 3D LUT into XMP Profile & Preset: {filter_name}")
