# NDS recompilation references, inspected 2026-11-06

| Project | Useful implementation boundary | Current decision |
| --- | --- | --- |
| RetroPortingToolKit/ndsrecomp, 54967a4e26bcd6ad46445d51bab3214decc3fd59 | ARMv5TE/ARMv4T to C, two-CPU scheduler, bus, device models, title-bank ABI | Pinned submodule; recompiler and ARMv5TE test built on macOS arm64 |
| Myth7x/ndsrecomp | Standalone ROM-to-C/CMake generator, software screens, SDL3 diagnostics | Reference only; documented audio/overlay gaps do not justify replacing the fuller runtime |
| mstan/supermario64dsrecomp | Exact-ROM title project, generated banks separate from source, content checks | Reference for title preparation and bank registration |
| GoldieLeGenie/DQIV-DECOMP | Message-language loading, font/glyph call-chain tracing, source recovery | Analysis workflow reference; its resource format is not the FFTA2 format |
| Rurusachi/ffta2-editor | Archive hashing, packed IDX/PAK resources, western encoding | Resource parser cross-check; copied charset data retains MIT attribution |

The local nsp-dawrin checkout at 0c07408 was inspected read-only. Its current
handheld module has GBA and 3DS backends, with an AppKit window and frame callback.
No NDS backend was found there. No sibling source or process was changed.

Native recompilation is ARM32 guest code translated to C and compiled for the
host; the AArch64 NS executor cannot directly execute ARM9/ARM7 instructions.
A macOS host backend must separately provide dual-screen presentation, touch,
buttons, audio transport and host timing. Guest timers and IPC remain on the
shared event scheduler. macOS does not provide OpenGL 4.3 compute; the initial
parity renderer must remain the shared software renderer, with Metal as a
separate presentation/acceleration path. Shader translation for the NS GPU is
not an NDS renderer.

Status: native recompiler tool builds. No FFTA2 game bank or native game runtime
has been accepted. The DeSmuME probe is explicitly an independent emulator
oracle for ROM patch verification, not the native backend.

Upstream's recompiler now has PolyForm Noncommercial terms, while its runner
and several support directories retain MIT/GPL terms as documented upstream.
The new project's original source is GPL-3.0-or-later. These grants do not
relicense the submodule. Review exact component terms when packaging a runner.

Sources:
- https://github.com/RetroPortingToolKit/ndsrecomp
- https://github.com/Myth7x/ndsrecomp
- https://github.com/mstan/supermario64dsrecomp
- https://github.com/GoldieLeGenie/DQIV-DECOMP
- https://github.com/Rurusachi/ffta2-editor
