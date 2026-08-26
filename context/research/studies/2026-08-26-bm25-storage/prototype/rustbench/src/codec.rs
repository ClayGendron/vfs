//! LEB128 varints and the block codec: delta-coded doc ids, raw tfs and dls.

#[inline]
pub fn put_varint(out: &mut Vec<u8>, mut value: u64) {
    while value >= 0x80 {
        out.push((value as u8 & 0x7F) | 0x80);
        value >>= 7;
    }
    out.push(value as u8);
}

/// Decode every varint in `blob` into `out` (appending); returns the count.
#[inline]
pub fn decode_varints(blob: &[u8], out: &mut Vec<u64>) -> usize {
    let mut n = 0;
    let mut value: u64 = 0;
    let mut shift = 0;
    for &b in blob {
        value |= ((b & 0x7F) as u64) << shift;
        if b & 0x80 == 0 {
            out.push(value);
            n += 1;
            value = 0;
            shift = 0;
        } else {
            shift += 7;
        }
    }
    n
}

/// Decode a delta-coded id blob into absolute ids (appending).
#[inline]
pub fn decode_deltas(blob: &[u8], out: &mut Vec<i64>) -> usize {
    let mut n = 0;
    let mut value: u64 = 0;
    let mut shift = 0;
    let mut prev: i64 = 0;
    for &b in blob {
        value |= ((b & 0x7F) as u64) << shift;
        if b & 0x80 == 0 {
            prev += value as i64;
            out.push(prev);
            n += 1;
            value = 0;
            shift = 0;
        } else {
            shift += 7;
        }
    }
    n
}
