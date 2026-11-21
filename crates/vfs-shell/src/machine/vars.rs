//! Shell variables: a global table and a stack of function scopes searched
//! innermost first (bash's dynamic scope), each variable with its
//! attributes. An associative array keeps bash's own iteration order: its
//! keys sit in hash buckets, newest first in each, walked bucket by bucket.

use std::collections::BTreeMap;

pub const INTEGER: u16 = 1;
pub const LOWER: u16 = 2;
pub const UPPER: u16 = 4;
pub const READONLY: u16 = 8;
pub const EXPORT: u16 = 16;
pub const NAMEREF: u16 = 32;
pub const INDEXED: u16 = 64;
pub const ASSOC: u16 = 128;
pub const TRACE: u16 = 256;
pub const CAPITALIZE: u16 = 512;

/// The buckets a new associative array starts with, as bash's.
const ASSOC_BUCKETS: usize = 1024;
/// An associative array grows when it holds this many entries per bucket.
const GROW_FACTOR: usize = 2;
/// And grows by this multiple.
const GROW_MULTIPLE: usize = 4;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Value {
    Scalar(String),
    Indexed(BTreeMap<i64, String>),
    Assoc(AssocMap),
}

impl Value {
    /// Bytes this value holds, as the memory count sees it.
    pub fn footprint(&self) -> usize {
        match self {
            Value::Scalar(text) => text.len(),
            Value::Indexed(map) => map.values().map(|v| v.len().saturating_add(16)).sum(),
            Value::Assoc(map) => map
                .iter()
                .map(|(k, v)| k.len().saturating_add(v.len()).saturating_add(16))
                .sum(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Var {
    /// `None` is a variable declared with attributes but no value.
    pub value: Option<Value>,
    pub attrs: u16,
}

impl Var {
    pub fn scalar(text: String) -> Var {
        Var {
            value: Some(Value::Scalar(text)),
            attrs: 0,
        }
    }

    pub fn has(&self, attr: u16) -> bool {
        self.attrs & attr != 0
    }

    pub fn is_array(&self) -> bool {
        matches!(self.value, Some(Value::Indexed(_) | Value::Assoc(_)))
            || self.has(INDEXED)
            || self.has(ASSOC)
    }

    pub fn is_assoc(&self) -> bool {
        matches!(self.value, Some(Value::Assoc(_))) || self.has(ASSOC)
    }

    pub fn footprint(&self) -> usize {
        self.value
            .as_ref()
            .map_or(0, Value::footprint)
            .saturating_add(32)
    }
}

/// One function call's local variables. A `None` entry is a local that was unset.
#[derive(Clone, Debug, Default)]
pub struct Scope {
    pub vars: BTreeMap<String, Option<Var>>,
}

#[derive(Clone, Debug, Default)]
pub struct Vars {
    pub global: BTreeMap<String, Var>,
    pub scopes: Vec<Scope>,
}

/// Where a name resolves.
pub enum Slot {
    Local(usize),
    Global,
    Nowhere,
}

impl Vars {
    pub fn slot(&self, name: &str) -> Slot {
        for (index, scope) in self.scopes.iter().enumerate().rev() {
            if let Some(entry) = scope.vars.get(name) {
                return match entry {
                    Some(_) => Slot::Local(index),
                    // An unset local hides the global until the function returns.
                    None => Slot::Local(index),
                };
            }
        }
        if self.global.contains_key(name) {
            Slot::Global
        } else {
            Slot::Nowhere
        }
    }

    pub fn get(&self, name: &str) -> Option<&Var> {
        match self.slot(name) {
            Slot::Local(index) => self.scopes.get(index)?.vars.get(name)?.as_ref(),
            Slot::Global => self.global.get(name),
            Slot::Nowhere => None,
        }
    }

    pub fn get_mut(&mut self, name: &str) -> Option<&mut Var> {
        match self.slot(name) {
            Slot::Local(index) => self.scopes.get_mut(index)?.vars.get_mut(name)?.as_mut(),
            Slot::Global => self.global.get_mut(name),
            Slot::Nowhere => None,
        }
    }

    /// The variable `name`, created where an assignment would put it.
    pub fn entry(&mut self, name: &str) -> &mut Var {
        let slot = self.slot(name);
        if let Slot::Local(index) = slot {
            if let Some(scope) = self.scopes.get_mut(index) {
                let entry = scope.vars.entry(name.to_owned()).or_insert(None);
                return entry.get_or_insert_with(|| Var {
                    value: None,
                    attrs: 0,
                });
            }
        }
        self.global.entry(name.to_owned()).or_insert(Var {
            value: None,
            attrs: 0,
        })
    }

    /// Make `name` local to the innermost function, returning it.
    pub fn local(&mut self, name: &str) -> Option<&mut Var> {
        let scope = self.scopes.last_mut()?;
        let entry = scope.vars.entry(name.to_owned()).or_insert(None);
        Some(entry.get_or_insert_with(|| Var {
            value: None,
            attrs: 0,
        }))
    }

    pub fn is_local_here(&self, name: &str) -> bool {
        self.scopes
            .last()
            .is_some_and(|scope| scope.vars.contains_key(name))
    }

    /// Remove `name`: a local stays as an unset local of its function.
    pub fn unset(&mut self, name: &str) {
        match self.slot(name) {
            Slot::Local(index) => {
                let innermost = self.scopes.len().saturating_sub(1);
                if let Some(scope) = self.scopes.get_mut(index) {
                    if index == innermost {
                        scope.vars.insert(name.to_owned(), None);
                    } else {
                        // A callee unsetting a caller's local reveals what lies beneath.
                        scope.vars.remove(name);
                    }
                }
            }
            Slot::Global => {
                self.global.remove(name);
            }
            Slot::Nowhere => {}
        }
    }

    /// Every visible name, sorted.
    pub fn names(&self) -> Vec<String> {
        let mut names: BTreeMap<String, ()> = BTreeMap::new();
        for name in self.global.keys() {
            names.insert(name.clone(), ());
        }
        for scope in &self.scopes {
            for name in scope.vars.keys() {
                names.insert(name.clone(), ());
            }
        }
        names
            .into_keys()
            .filter(|name| self.get(name).is_some())
            .collect()
    }
}

// ---------------------------------------------------------------------------
// Associative arrays in bash's order
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AssocMap {
    buckets: Vec<Vec<(String, String)>>,
    len: usize,
}

impl Default for AssocMap {
    fn default() -> Self {
        AssocMap::new()
    }
}

impl AssocMap {
    pub fn new() -> AssocMap {
        AssocMap {
            buckets: vec![Vec::new(); ASSOC_BUCKETS],
            len: 0,
        }
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    fn bucket_of(&self, key: &str) -> usize {
        let mask = self.buckets.len().saturating_sub(1);
        usize::try_from(fnv1(key)).unwrap_or(0) & mask
    }

    pub fn get(&self, key: &str) -> Option<&String> {
        let bucket = self.buckets.get(self.bucket_of(key))?;
        bucket.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    pub fn insert(&mut self, key: String, value: String) {
        let index = self.bucket_of(&key);
        if let Some(bucket) = self.buckets.get_mut(index) {
            if let Some(slot) = bucket.iter_mut().find(|(k, _)| *k == key) {
                slot.1 = value;
                return;
            }
        }
        if self.len >= self.buckets.len().saturating_mul(GROW_FACTOR) {
            self.grow();
        }
        let index = self.bucket_of(&key);
        if let Some(bucket) = self.buckets.get_mut(index) {
            // Newest first in its bucket.
            bucket.insert(0, (key, value));
            self.len = self.len.saturating_add(1);
        }
    }

    fn grow(&mut self) {
        let size = self.buckets.len().saturating_mul(GROW_MULTIPLE);
        let old = std::mem::replace(&mut self.buckets, vec![Vec::new(); size]);
        for bucket in old {
            for (key, value) in bucket {
                let index = self.bucket_of(&key);
                if let Some(target) = self.buckets.get_mut(index) {
                    target.insert(0, (key, value));
                }
            }
        }
    }

    pub fn remove(&mut self, key: &str) -> Option<String> {
        let index = self.bucket_of(key);
        let bucket = self.buckets.get_mut(index)?;
        let at = bucket.iter().position(|(k, _)| k == key)?;
        self.len = self.len.saturating_sub(1);
        Some(bucket.remove(at).1)
    }

    /// Entries in bash's iteration order.
    pub fn iter(&self) -> impl Iterator<Item = (&String, &String)> {
        self.buckets
            .iter()
            .flat_map(|bucket| bucket.iter().map(|(k, v)| (k, v)))
    }
}

/// Bash's string hash: 32-bit FNV-1.
fn fnv1(text: &str) -> u32 {
    let mut hash: u32 = 2_166_136_261;
    for byte in text.bytes() {
        hash = hash.wrapping_mul(16_777_619);
        // Bash hashes through a signed `char`, so a high byte is sign-extended.
        hash ^= i32::from(byte as i8) as u32;
    }
    hash
}
