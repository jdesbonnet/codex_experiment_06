//! Hardware-equivalent regression for the wasm sim.
//!
//! For each .cvm.c under `projects/tiny_vm/tests/`, compile with `vm_cc.py`,
//! run through our pure-Rust `TinyVm`, and assert the stdout matches the
//! `expected_lines()` already used by `tools/test_tiny_vm_hardware.py`.
//!
//! This is the M1 acceptance bar: parity with the Python sim and the
//! on-MCU runtime for every committed test program.

use std::path::PathBuf;
use std::process::Command;

use tiny_vm_sim::{
    TinyVm, STATUS_HALT, STATUS_HOST_PENDING, STATUS_OK,
};

fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR is .../tools/vscode/sim/rust at test time.
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .ancestors()
        .nth(4)
        .expect("manifest is at least 4 levels deep")
        .to_path_buf()
}

fn compile_case(name: &str) -> Vec<u8> {
    let root = repo_root();
    let src = root.join(format!("projects/tiny_vm/tests/{}.cvm.c", name));
    let out = std::env::temp_dir().join(format!("regression_{}.bin", name));
    // vm_cc.py shells out to tools/vm_asm.py with a relative path, so the
    // working directory has to be the repo root for compilation to succeed.
    let status = Command::new("python3")
        .arg(root.join("tools/vm_cc.py"))
        .arg(&src)
        .arg("-o")
        .arg(&out)
        .current_dir(&root)
        .status()
        .expect("invoke vm_cc.py");
    assert!(status.success(), "vm_cc.py failed for {}", name);
    std::fs::read(&out).expect("read compiled bin")
}

/// Mirror of DefaultHostCalls in tools/theia/sim/host_calls.py: only the
/// stdout side-effects matter for these tests. LED and DELAY pop their arg
/// and do nothing observable.
fn run_program(code: &[u8]) -> (i32, Vec<String>) {
    let mut vm = TinyVm::new(code).expect("bytecode under CODE_MAX");
    let mut stdout: Vec<String> = Vec::new();
    loop {
        let status = vm.run(10_000_000);
        if status == STATUS_HOST_PENDING {
            let host_id = vm.pending_host_id() as u8;
            let rc = match host_id {
                0 | 1 => {
                    // LED_WRITE / DELAY_MS: pop the arg, no stdout.
                    if vm.pop().is_err() { -1 } else { 0 }
                }
                2 => match vm.pop() {
                    Ok(v) => { stdout.push(format!("{}\n", v)); 0 }
                    Err(_) => -1,
                },
                3 => match vm.pop() {
                    Ok(v) => { stdout.push(format!("{:08X}\n", v as u32)); 0 }
                    Err(_) => -1,
                },
                _ => -1,
            };
            vm.complete_host_call(rc);
            continue;
        }
        return (status, stdout);
    }
}

fn primes_upto(limit: u32) -> Vec<u32> {
    let mut out = Vec::new();
    'outer: for n in 2..=limit {
        let mut d = 2u32;
        while d.saturating_mul(d) <= n {
            if n % d == 0 { continue 'outer; }
            d += 1;
        }
        out.push(n);
    }
    out
}

fn expected_lines(name: &str) -> Vec<String> {
    match name {
        "count10" => (1..=10).map(|i| i.to_string()).collect(),
        "primes1000" => primes_upto(1000).iter().map(|n| n.to_string()).collect(),
        "collatz_max" => vec!["97".into(), "118".into()],
        "checksum8" => vec!["15".into()],
        "crc32" => vec!["CBF43926".into()],
        "rotate32" => vec!["34567812".into(), "78123456".into()],
        "mem32" => vec!["12345678".into(), "A5A5A5A5".into()],
        "sha1_abc" => vec![
            "A9993E36".into(),
            "4706816A".into(),
            "BA3E2571".into(),
            "7850C26C".into(),
            "9CD0D89D".into(),
        ],
        _ => panic!("unknown test case: {}", name),
    }
}

fn check_case(name: &str) {
    let bin = compile_case(name);
    let (status, stdout) = run_program(&bin);
    assert_eq!(
        status, STATUS_HALT,
        "{}: expected HALT, got {} (with output {:?})",
        name, status, stdout,
    );
    // Strip trailing newlines, match the per-line expectation.
    let actual: Vec<String> = stdout.iter().map(|s| s.trim_end().to_string()).collect();
    let expected = expected_lines(name);
    assert_eq!(actual, expected, "{}: output mismatch", name);
    // Silence unused-import warning for STATUS_OK on success paths.
    let _ = STATUS_OK;
}

#[test] fn case_count10()    { check_case("count10"); }
#[test] fn case_primes1000() { check_case("primes1000"); }
#[test] fn case_collatz_max(){ check_case("collatz_max"); }
#[test] fn case_checksum8()  { check_case("checksum8"); }
#[test] fn case_crc32()      { check_case("crc32"); }
#[test] fn case_rotate32()   { check_case("rotate32"); }
#[test] fn case_mem32()      { check_case("mem32"); }
#[test] fn case_sha1_abc()   { check_case("sha1_abc"); }
