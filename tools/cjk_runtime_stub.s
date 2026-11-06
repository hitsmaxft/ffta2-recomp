/* Experimental font-heap code, loaded at image + 0x2000. ARM9 only. */
.syntax unified
.arm
.global cjk_stub
cjk_stub:
    ldr ip, =0x0204c2e0
    cmp lr, ip
    beq preserve_glyph_bank
    ldr ip, =0x0204dd1c
    cmp lr, ip
    beq trace_line_copy
    ldr ip, =0x0204d830
    cmp lr, ip
    beq preserve_layout_control
    ldr ip, =0x0204d478
    cmp lr, ip
    beq preserve_control
    adr ip, trace
    str lr, [ip]
    /* Only direct ordinary-glyph rendering in sub_0204D500 has the
       expected text base at caller's sp+4 and byte index in r5. */
    ldr ip, =0x0204d618
    cmp lr, ip
    bne original
    push {r0, r1}
    ldr r0, [sp, #68]
    adr r1, trace
    str r0, [r1, #48]
    pop {r0, r1}
    push {r0}
    ldr r0, [sp, #64]
    ldr ip, =0x0204c0f4
    cmp r0, ip
    pop {r0}
    bne original
    cmp r0, #0xa9
    blo original
    cmp r0, #0xbf
    bhi original
    push {r0-r12, lr}
    adr ip, trace
    str lr, [ip, #4]
    ldr r4, [sp, #92] /* D500 saved caller r6, pointer to object+0x14 */
    add r4, r4, #0x11
    ldrb r4, [r4, r5, lsl #2]
    cmp r4, #1
    blo invalid
    cmp r4, #114
    bhi invalid
    sub r4, r4, #1
    mov r5, #23
    mul r4, r5, r4
    sub r5, r0, #0xa9
    add r4, r4, r5
    ldr ip, =2613
    cmp r4, ip
    bhs invalid
    mov r5, r1
    adr r0, filename
    ldr ip, =0x0201fe38
    blx ip
    cmp r0, #0
    beq invalid
    adr ip, trace
    str r0, [ip, #8]
    mov r6, r0
    mov r1, r5
    mov r2, r4, lsl #6
    mov r3, #64
    ldr ip, =0x0201ff84
    blx ip
    adr ip, trace
    mov r0, #2
    str r0, [ip, #12]
wait_read:
    mov r0, #1
    ldr ip, =0x0201e21c
    blx ip
    mov r0, r6
    ldr ip, =0x02020000
    blx ip
    cmp r0, #1
    bne wait_read
    adr ip, trace
    mov r0, #3
    str r0, [ip, #12]
    mov r0, r6
    ldr ip, =0x0201ffe8
    blx ip
    pop {r0-r12, pc}
invalid:
    pop {r0-r12, lr}
original:
    /* Four instructions displaced at the original 0x020845f0 entry. */
    push {r3, r4, r5, r6, r7, r8, r9, lr}
    mov r6, r1
    mov r5, r2
    mov r4, r3
    ldr pc, =0x02084600
preserve_control:
    adr ip, trace
    str lr, [ip, #28]
    /* sub_0204D34C discarded unknown control pairs. Preserve D0 in the
       bounded line buffer so the following glyph can recover its bank. */
    ldr r0, [r9, #12]
    ldrb r1, [r0, r7]
    cmp r1, #0xd0
    bne skip_control
    strb r1, [r4, r8]
    add r8, r8, #1
    add r7, r7, #1
    ldrb r1, [r0, r7]
    strb r1, [r4, r8]
    add r8, r8, #1
    add r7, r7, #1
    ldr pc, =0x0204d490
skip_control:
    add r7, r7, #2
    ldr pc, =0x0204d490
preserve_layout_control:
    adr ip, trace
    str lr, [ip, #32]
    ldrb r1, [r5]
    str r1, [ip, #36]
    cmp r1, #0xd0
    bne layout_original
    add r0, sp, #0x92
    strb r1, [r0, r8]
    add r0, sp, #0xd0
    str r6, [r0, r8, lsl #2]
    mov r0, #0
    strb r0, [r4, r8]
    add r8, r8, #1
    ldrb r1, [r5, #1]
    add r0, sp, #0x92
    strb r1, [r0, r8]
    add r0, sp, #0xd0
    str r6, [r0, r8, lsl #2]
    mov r0, #0
    strb r0, [r4, r8]
    add r8, r8, #1
    add r5, r5, #2
    ldr pc, =0x0204dc70
layout_original:
    ldr pc, =0x0204db88
preserve_glyph_bank:
    /* At C2DC, r5 is the control parameter, r7 the visible glyph index. */
    ldr r0, [sp]
    ldr r0, [r0, #12]
    ldrb r0, [r0, r11]
    cmp r0, #0xd0
    bne bank_original
    add r0, r9, #0x25
    strb r5, [r0, r7, lsl #2]
bank_original:
    ldr pc, =0x0204c4bc
trace_line_copy:
    adr ip, trace
    str r0, [ip, #40]
    str r1, [ip, #44]
    ldr pc, =0x0204abd0
    .align 2
filename:
    .asciz "menu/font/CJKtest4.bin"
    .align 2
    .ltorg
trace:
    .word 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
