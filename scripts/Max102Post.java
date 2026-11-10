// MAX102 (WB32FQ95) Ghidra post-script
// 建向量表符号、创建函数、标注外设与字符串
//@category MAX102

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.*;

public class Max102Post extends GhidraScript {

    static final long FLASH_BASE = 0x08000000L;

    static final String[][] SYSVEC = {
        {"Reset_Handler"}, {"NMI_Handler"}, {"HardFault_Handler"},
        {"MemManage_Handler"}, {"BusFault_Handler"}, {"UsageFault_Handler"},
        {"Reserved7"}, {"Reserved8"}, {"Reserved9"}, {"Reserved10"},
        {"SVC_Handler"}, {"DebugMon_Handler"}, {"Reserved13"},
        {"PendSV_Handler"}, {"SysTick_Handler"}
    };

    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        SymbolTable st = currentProgram.getSymbolTable();
        FunctionManager fm = currentProgram.getFunctionManager();

        println("=== MAX102 post-analysis ===");

        // 1) 向量表
        Address vt = sp.getAddress(FLASH_BASE);
        int nVec = 0;
        for (int i = 0; i < 256; i++) {
            long va = FLASH_BASE + 4L * i;
            Address a = sp.getAddress(va);
            long val;
            try {
                val = Integer.toUnsignedLong(mem.getInt(a));
            } catch (Exception e) { break; }

            if (i == 0) {
                st.createLabel(a, "Initial_SP", SourceType.USER_DEFINED);
                println(String.format("SP = 0x%08X", val));
                continue;
            }
            if (val == 0) break;
            if (val < FLASH_BASE || val >= FLASH_BASE + 0x20000) break;
            if ((val & 1) == 0) break;

            String name;
            if (i - 1 < SYSVEC.length) name = SYSVEC[i - 1][0];
            else name = String.format("IRQ%d_Handler", i - 1 - 15);

            // 向量表项本身起个名字
            st.createLabel(a, name + "_VEC", SourceType.USER_DEFINED);

            Address handler = sp.getAddress(val & ~1L);
            // 给 handler 建函数
            try {
                if (fm.getFunctionAt(handler) == null) {
                    createFunction(handler, name);
                } else {
                    st.createLabel(handler, name, SourceType.USER_DEFINED);
                }
            } catch (Exception e) {
                // ignore
            }
            nVec++;
        }
        println("vector entries: " + nVec);

        // 2) 递归下降反汇编（让 Ghidra 自己找函数）
        println("disassembling entry points ...");
        // 让 Ghidra 从向量表所有 handler 开始反汇编
        for (int i = 1; i < 64; i++) {
            long va = FLASH_BASE + 4L * i;
            Address a = sp.getAddress(va);
            long val;
            try { val = Integer.toUnsignedLong(mem.getInt(a)); } catch (Exception e) { break; }
            if (val == 0 || val < FLASH_BASE || (val & 1) == 0) break;
            Address h = sp.getAddress(val & ~1L);
            try { disassemble(h); } catch (Exception e) {}
        }

        // 3) 全段反汇编（逐地址，避免 API 签名问题）
        println("disassemble whole flash ...");
        int dis = 0;
        for (long va = FLASH_BASE; va < FLASH_BASE + 0x11000; ) {
            Address a = sp.getAddress(va);
            try {
                if (getInstructionAt(a) == null) {
                    boolean ok = disassemble(a);
                    if (!ok) { va += 2; continue; }
                    // 计算这条指令长度
                    Instruction ins = getInstructionAt(a);
                    int len = (ins != null) ? ins.getLength() : 2;
                    va += len;
                    dis++;
                } else {
                    va += getInstructionAt(a).getLength();
                }
            } catch (Exception e) {
                va += 2;
            }
        }
        println("newly disassembled: " + dis);

        // 4) 外设内存块（可选，仅打印已知地址引用）
        println("=== done ===");
    }
}
