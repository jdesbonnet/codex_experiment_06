#include "tiny_vm.h"

static int vm_read_u8(tiny_vm_t *vm, uint8_t *out)
{
    if (vm->pc >= vm->code_len) {
        return TINY_VM_ERR_PC_OOB;
    }
    *out = vm->code[vm->pc++];
    return TINY_VM_OK;
}

void tiny_vm_init(tiny_vm_t *vm, tiny_vm_host_call_t host_call, void *host_ctx)
{
    uint8_t i;
    vm->code_len = 0u;
    vm->pc = 0u;
    vm->sp = 0u;
    for (i = 0u; i < TINY_VM_LOCALS_MAX; i++) {
        vm->locals[i] = 0;
    }
    vm->host_call = host_call;
    vm->host_ctx = host_ctx;
}

int tiny_vm_load(tiny_vm_t *vm, const uint8_t *code, uint16_t code_len)
{
    uint16_t i;
    if (code_len > TINY_VM_CODE_MAX) {
        return TINY_VM_ERR_CODE_TOO_LARGE;
    }
    for (i = 0u; i < code_len; i++) {
        vm->code[i] = code[i];
    }
    vm->code_len = code_len;
    vm->pc = 0u;
    vm->sp = 0u;
    for (i = 0u; i < TINY_VM_LOCALS_MAX; i++) {
        vm->locals[i] = 0;
    }
    return TINY_VM_OK;
}

int tiny_vm_push(tiny_vm_t *vm, int32_t v)
{
    if (vm->sp >= TINY_VM_STACK_MAX) {
        return TINY_VM_ERR_STACK_OVERFLOW;
    }
    vm->stack[vm->sp++] = v;
    return TINY_VM_OK;
}

int tiny_vm_pop(tiny_vm_t *vm, int32_t *out)
{
    if (vm->sp == 0u) {
        return TINY_VM_ERR_STACK_UNDERFLOW;
    }
    vm->sp--;
    *out = vm->stack[vm->sp];
    return TINY_VM_OK;
}

int tiny_vm_exec(tiny_vm_t *vm, uint32_t step_budget)
{
    uint32_t steps = 0u;
    while (steps < step_budget) {
        uint8_t op = 0u;
        int32_t a = 0;
        int32_t b = 0;
        int rc = vm_read_u8(vm, &op);
        uint8_t imm = 0u;
        uint8_t lo = 0u;
        uint8_t hi = 0u;
        uint16_t target = 0u;

        if (rc < 0) {
            return rc;
        }

        switch (op) {
        case TINY_OP_NOP:
            break;
        case TINY_OP_PUSH8:
            rc = vm_read_u8(vm, &imm);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_push(vm, (int32_t)(int8_t)imm);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_ADD:
            rc = tiny_vm_pop(vm, &b);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_push(vm, a + b);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_SUB:
            rc = tiny_vm_pop(vm, &b);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_push(vm, a - b);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_DUP:
            if (vm->sp == 0u) {
                return TINY_VM_ERR_STACK_UNDERFLOW;
            }
            rc = tiny_vm_push(vm, vm->stack[vm->sp - 1u]);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_DROP:
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            (void)a;
            break;
        case TINY_OP_SWAP:
            if (vm->sp < 2u) {
                return TINY_VM_ERR_STACK_UNDERFLOW;
            }
            a = vm->stack[vm->sp - 1u];
            vm->stack[vm->sp - 1u] = vm->stack[vm->sp - 2u];
            vm->stack[vm->sp - 2u] = a;
            break;
        case TINY_OP_JMP:
            rc = vm_read_u8(vm, &lo);
            if (rc < 0) {
                return rc;
            }
            rc = vm_read_u8(vm, &hi);
            if (rc < 0) {
                return rc;
            }
            target = (uint16_t)(((uint16_t)hi << 8) | lo);
            if (target >= vm->code_len) {
                return TINY_VM_ERR_PC_OOB;
            }
            vm->pc = target;
            break;
        case TINY_OP_JZ:
            rc = vm_read_u8(vm, &lo);
            if (rc < 0) {
                return rc;
            }
            rc = vm_read_u8(vm, &hi);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            if (a == 0) {
                target = (uint16_t)(((uint16_t)hi << 8) | lo);
                if (target >= vm->code_len) {
                    return TINY_VM_ERR_PC_OOB;
                }
                vm->pc = target;
            }
            break;
        case TINY_OP_HOST:
            rc = vm_read_u8(vm, &imm);
            if (rc < 0) {
                return rc;
            }
            if (vm->host_call == 0) {
                return TINY_VM_ERR_HOST;
            }
            rc = vm->host_call(vm, imm, vm->host_ctx);
            if (rc < 0) {
                return TINY_VM_ERR_HOST;
            }
            break;
        case TINY_OP_LGET:
            rc = vm_read_u8(vm, &imm);
            if (rc < 0) {
                return rc;
            }
            if (imm >= TINY_VM_LOCALS_MAX) {
                return TINY_VM_ERR_BAD_OPCODE;
            }
            rc = tiny_vm_push(vm, vm->locals[imm]);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_LSET:
            rc = vm_read_u8(vm, &imm);
            if (rc < 0) {
                return rc;
            }
            if (imm >= TINY_VM_LOCALS_MAX) {
                return TINY_VM_ERR_BAD_OPCODE;
            }
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            vm->locals[imm] = a;
            break;
        case TINY_OP_EQ:
            rc = tiny_vm_pop(vm, &b);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_push(vm, (a == b) ? 1 : 0);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_LT:
            rc = tiny_vm_pop(vm, &b);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_pop(vm, &a);
            if (rc < 0) {
                return rc;
            }
            rc = tiny_vm_push(vm, (a < b) ? 1 : 0);
            if (rc < 0) {
                return rc;
            }
            break;
        case TINY_OP_HALT:
            return TINY_VM_HALT;
        default:
            return TINY_VM_ERR_BAD_OPCODE;
        }

        steps++;
    }

    return TINY_VM_STEP_LIMIT;
}
