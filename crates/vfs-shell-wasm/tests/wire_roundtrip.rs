//! Every request the module writes, the host reads back as the same request, and every reply
//! the host writes, the module reads back as the same reply.
#![allow(clippy::unwrap_used, clippy::panic)]

use shell::machine::{Entry, EntryKind, HostError, Reply, Request, RequestKey, WriteMode};
use shell_wasm::wire;

fn key(ordinal: u32) -> RequestKey {
    RequestKey {
        task: vec![0, 2],
        ordinal,
    }
}

#[test]
fn every_request_reads_back_as_itself() {
    let requests = vec![
        Request::Read {
            path: "/a b".to_owned(),
            offset: 3,
            length: 9,
        },
        Request::Write {
            path: "/w".to_owned(),
            data: vec![0, 255, 10],
            mode: WriteMode::Append,
        },
        Request::Touch {
            path: "/t".to_owned(),
        },
        Request::Stat {
            path: "/s\"q".to_owned(),
        },
        Request::List {
            path: "/".to_owned(),
        },
        Request::Mkdir {
            path: "/m".to_owned(),
            parents: true,
        },
        Request::Remove {
            path: "/r".to_owned(),
            recursive: false,
        },
        Request::Copy {
            from: "/c".to_owned(),
            to: "/d".to_owned(),
            recursive: true,
        },
        Request::Move {
            from: "/m".to_owned(),
            to: "/n".to_owned(),
        },
        Request::Value {
            name: "time".to_owned(),
        },
        Request::Start {
            name: "search".to_owned(),
            args: vec!["x y".to_owned(), String::new()],
            cwd: "/work".to_owned(),
        },
        Request::Feed {
            program: key(4),
            data: b"chunk\n".to_vec(),
            eof: true,
        },
    ];
    for (ordinal, request) in requests.into_iter().enumerate() {
        let key = key(u32::try_from(ordinal).unwrap());
        let text = wire::encode_request(&key, &request);
        let parsed = wire::parse(&text).unwrap();
        assert_eq!(
            wire::decode_request(&parsed),
            Some((key, request)),
            "{text}"
        );
    }
}

#[test]
fn every_reply_reads_back_as_itself() {
    let replies = vec![
        (
            key(0),
            Reply::Data {
                bytes: vec![1, 2, 200],
                eof: true,
            },
        ),
        (key(1), Reply::Done),
        (
            key(2),
            Reply::Stat {
                kind: EntryKind::Directory,
                size: 7,
            },
        ),
        (
            key(3),
            Reply::Entries(vec![Entry {
                name: "a".to_owned(),
                kind: EntryKind::File,
            }]),
        ),
        (key(4), Reply::Text("t".to_owned())),
        (key(5), Reply::Error(HostError::NotEmpty)),
        (key(6), Reply::Library),
        (key(7), Reply::Started),
        (
            key(8),
            Reply::Output {
                stdout: b"o".to_vec(),
                stderr: b"e".to_vec(),
                status: Some(3),
            },
        ),
        (
            key(9),
            Reply::Output {
                stdout: Vec::new(),
                stderr: Vec::new(),
                status: None,
            },
        ),
        (
            key(10),
            Reply::Refused {
                status: 126,
                message: "no \"net\"".to_owned(),
            },
        ),
    ];
    let text = wire::encode_replies(&replies);
    assert_eq!(wire::decode_replies(&text).unwrap(), replies, "{text}");
}

#[test]
fn a_steps_statuses_read_back_as_themselves() {
    use shell::machine::{Status, Step};
    let step = Step {
        output: Vec::new(),
        requests: Vec::new(),
        status: Status::Done(3),
        statuses: vec![vec![1, 0], vec![255], Vec::new()],
    };
    let read = wire::decode_step(&wire::encode_step(&step, 7)).unwrap();
    assert_eq!(read.statuses, step.statuses);
    assert_eq!(read.status, wire::WireStatus::Done(3));
    assert_eq!(read.memory, 7);
}
