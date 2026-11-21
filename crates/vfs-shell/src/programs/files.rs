//! The file programs, written against the machine's own requests.

use super::Prog;
use crate::machine::Flow;

macro_rules! later {
    ($($name:ident),*) => {$(
        pub async fn $name(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
            let _ = args;
            prog.err("not yet implemented").await?;
            Ok(1)
        }
    )*};
}
later!(ls, find, cp, mv, rm, mkdir, touch);
