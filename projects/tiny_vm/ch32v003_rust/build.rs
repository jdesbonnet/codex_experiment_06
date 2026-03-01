use std::fs;
use std::path::Path;

fn main() {
    let out = std::env::var("OUT_DIR").unwrap();
    let src = Path::new("memory.x");
    let dst = Path::new(&out).join("memory.x");
    fs::copy(src, &dst).unwrap();
    println!("cargo:rustc-link-search={}", out);
}
