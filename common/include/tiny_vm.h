#ifndef TINY_VM_H
#define TINY_VM_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    TINY_VM_OK = 0,
    TINY_VM_HALT = 1,
    TINY_VM_STEP_LIMIT = 2,
    TINY_VM_ERR_PC_OOB = -1,
    TINY_VM_ERR_STACK_OVERFLOW = -2,
    TINY_VM_ERR_STACK_UNDERFLOW = -3,
    TINY_VM_ERR_BAD_OPCODE = -4,
    TINY_VM_ERR_HOST = -5,
    TINY_VM_ERR_CODE_TOO_LARGE = -6,
    TINY_VM_ERR_MEM_OOB = -7
} tiny_vm_status_t;

typedef enum {
    TINY_OP_NOP = 0x00,
    TINY_OP_PUSH8 = 0x01,
    TINY_OP_ADD = 0x02,
    TINY_OP_SUB = 0x03,
    TINY_OP_DUP = 0x04,
    TINY_OP_DROP = 0x05,
    TINY_OP_SWAP = 0x06,
    TINY_OP_JMP = 0x07,
    TINY_OP_JZ = 0x08,
    TINY_OP_HOST = 0x09,
    TINY_OP_LGET = 0x0A,
    TINY_OP_LSET = 0x0B,
    TINY_OP_EQ = 0x0C,
    TINY_OP_LT = 0x0D,
    TINY_OP_PUSH16 = 0x0E,
    TINY_OP_MOD = 0x0F,
    TINY_OP_MUL = 0x10,
    TINY_OP_DIV = 0x11,
    TINY_OP_MGET = 0x12,
    TINY_OP_MSET = 0x13,
    TINY_OP_HALT = 0xFF
} tiny_vm_opcode_t;

#define TINY_VM_STACK_MAX 16u
#define TINY_VM_CODE_MAX 256u
#define TINY_VM_LOCALS_MAX 16u
#define TINY_VM_MEM_MAX 64u

struct tiny_vm;
typedef int (*tiny_vm_host_call_t)(struct tiny_vm *vm, uint8_t id, void *ctx);

typedef struct tiny_vm {
    uint8_t code[TINY_VM_CODE_MAX];
    uint16_t code_len;
    uint16_t pc;
    int32_t stack[TINY_VM_STACK_MAX];
    int32_t locals[TINY_VM_LOCALS_MAX];
    uint8_t mem[TINY_VM_MEM_MAX];
    uint8_t sp;
    tiny_vm_host_call_t host_call;
    void *host_ctx;
} tiny_vm_t;

void tiny_vm_init(tiny_vm_t *vm, tiny_vm_host_call_t host_call, void *host_ctx);
int tiny_vm_load(tiny_vm_t *vm, const uint8_t *code, uint16_t code_len);
int tiny_vm_exec(tiny_vm_t *vm, uint32_t step_budget);

int tiny_vm_push(tiny_vm_t *vm, int32_t v);
int tiny_vm_pop(tiny_vm_t *vm, int32_t *out);

#endif
