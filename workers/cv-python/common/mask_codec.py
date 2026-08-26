import gzip
import struct
from typing import NamedTuple

MAGIC = b"PAQ1"

class DecodedMask(NamedTuple):
    width: int
    height: int
    class_ids: list[int]
    rle_runs: list[list[int]]

CLASS_TABLE = {"vehicle": 1, "person": 2, "animal": 3, "boat": 4, "aircraft": 5}

def encode_mask_paq(width: int, height: int, class_masks: dict[str, "np.ndarray"]) -> bytes:
    body = bytearray()
    body += struct.pack("<HHB", width, height, len(class_masks))
    for name, mask in class_masks.items():
        class_id = CLASS_TABLE[name]
        flat = mask.flatten(order="C")
        runs = _binary_rle(flat)
        body += struct.pack("<BI", class_id, len(runs))
        body += struct.pack(f"<{len(runs)}I", *runs)
    return MAGIC + gzip.compress(bytes(body), compresslevel=6)

def decode_mask_paq(data: bytes) -> DecodedMask:
    if data[:4] != MAGIC:
        raise ValueError("bad .paq magic")
    body = gzip.decompress(data[4:])
    width, height, num_classes = struct.unpack_from("<HHB", body, 0)
    offset = 5
    class_ids, rle_runs = [], []
    for _ in range(num_classes):
        class_id, num_runs = struct.unpack_from("<BI", body, offset)
        offset += 5
        runs = list(struct.unpack_from(f"<{num_runs}I", body, offset))
        offset += num_runs * 4
        class_ids.append(class_id)
        rle_runs.append(runs)
    return DecodedMask(width, height, class_ids, rle_runs)

def _binary_rle(flat_bool: "np.ndarray") -> list[int]:
    runs, current, count = [], 0, 0
    for v in flat_bool:
        if v == current:
            count += 1
        else:
            runs.append(count)
            current, count = v, 1
    runs.append(count)
    return runs
