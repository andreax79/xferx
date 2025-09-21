# Copyright (C) 2414 Andrea Bonomi <andrea.bonomi@gmail.com>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# https://bitsavers.org/pdf/dec/pdp7/F-75_PDP-7userHbk_Jun65.pdf Pag 203

import typing as t
from dataclasses import dataclass

GROUP1_OP = 0o74  # Group 1 Operate Instructions
GROUP2_OP = 0o76  # Group 2 Operate Instructions (LAW)

OPCODES = {
    # Memory reference instructions
    0o00: ("CAL", "Call subroutine."),
    0o04: ("DAC", "Deposit AC."),
    0o10: ("JMS", "Jump to subroutine."),
    0o14: ("DZM", "Deposit zero in memory."),
    0o20: ("LAC", "Load AC."),
    0o24: ("XOR", "Exclusive OR."),
    0o30: ("ADD", "One's complement add."),
    0o34: ("TAD", "Two's complement add."),
    0o40: ("XCT", "Execute."),
    0o44: ("ISZ", "Increment and skip if zero."),
    0o50: ("AND", "Logical AND."),
    0o54: ("SAD", "Skip if AC is different from Y."),
    0o60: ("JMP", "Jump to Y."),
    # EAE instruction list
    0o640000: ("EAE", "Basic EAE command."),
    0o640500: ("LRS", "Long right shift."),
    0o660500: ("LRSS", "Long right shift, signed (AC sign = link)."),
    0o640600: ("LLS", "Long left shift."),
    0o660600: ("LLSS", "Long left shift, signed (AC sign = L)."),
    0o640700: ("ALS", "Accumulator left shift."),
    0o660700: ("ALSS", "Accumulator left shift, signed (AC sign = L)."),
    0o640444: ("NORM", "Normalize, unsigned."),
    0o660444: ("NORMS", "Normalize, signed (AC sign =L)."),
    0o653122: ("MUL", "Multiply, unsigned."),
    0o657122: ("MULS", "Multiply, signed."),
    0o640323: ("DIV", "Divide, unsigned."),
    0o644323: ("DIVS", "Divide, signed."),
    0o653323: ("IDIV", "Integer divide, unsigned."),
    0o657323: ("IDIVS", "Integer divide, signed."),
    0o650323: ("FRDIV", "Fraction divide, unsigned."),
    0o654323: ("FRDIVS", "Fraction divide, signed."),
    0o641002: ("LACQ", "Replace the content of the AC with the content of the MQ."),
    0o641001: ("LACS", "Replace the content of the AC with the content of the SC."),
    0o650000: ("CLQ", "Clear MQ."),
    0o644000: ("ABS", "Place absolute value of AC in the AC."),
    0o664000: ("GSM", "Get sign and magnitude."),
    0o640001: ("OSC", "Inclusive OR the SC into the AC."),
    0o640002: ("OMQ", "Inclusive OR AC with MQ and place results in AC."),
    0o640004: ("CMQ", "Complement the MQ."),
    0o652000: ("LMQ", "Load MQ"),
    # Input/output transfer instructions
    # Program Interrupt
    0o700002: ("IOF", "Interrupt off."),
    0o700042: ("ION", "Interrupt on."),
    0o700062: ("ITON", "Interrupt and trap on."),
    # Real Time Clock
    0o700001: ("CLSF", "Skip the next instruction if the clock flag is set to 1."),
    # 0o700004: ("CLOF", "Clear the clock flag and disable the clock."), - duplicated
    # 0o700044: ("CLON", "Clear the clock flag and enable the clock."), - duplicated
    # Perforated Tape Reader
    0o700101: ("RSF", "Skip if reader flag is a 1."),
    0o700102: ("RCF", "Clear reader flag, then inclusively OR the content of reader buffer into the AC."),
    0o700112: ("RRB", "Read reader buffer."),
    0o700104: ("RSA", "Select reader in alphanumeric mode."),
    0o700144: ("RSB", "Select reader in binary mode."),
    # Perforated Tape Punch
    0o700201: ("PSF", "Skip if the punch flag is set to 1."),
    0o700202: ("PCF", "Clear the punch flag."),
    0o700204: ("PSA", "Punch a line of tape in alphanumeric mode."),
    0o700206: ("PLS", ""),
    0o700244: ("PSB", "Punch a line of tape in binary mode."),
    # I/O Equipment
    0o700314: ("I/ORS", "Input/output read status."),
    0o703301: ("TTS", "Test Teletype and skip if KSR 33 is connected to computer."),
    0o703302: ("CAF", "Clear all flags."),
    0o703341: ("SKP7", "Skip if processor is a PDP-7."),
    # Teletype Keyboard
    0o700301: ("KSF", "Skip if the keyboard flag is set to 1."),
    0o700312: ("KRB", "Read the keyboard buffer."),
    # Teletype Teleprinter
    0o700401: ("TSF", "Skip if the teleprinter flag is set."),
    0o700402: ("TCF", "Clear the teleprinter flag."),
    0o700406: ("TLS", "Load teleprinter buffer."),
    # Oscilloscope and Precision CRT Displays
    0o700502: ("DXC", "Clear the X-coordinate buffer."),
    0o700602: ("DYC", "Clear the Y-coordinate buffer."),
    0o700506: ("DXL", "Load the X-coordinate buffer from AC8-17."),
    # 0o700606: ("DYL", "Load the Y-coordinate buffer from AC8-17."),  # duplicated
    0o700546: ("DXS", "Load the X-coordinate buffer and display the point specified by the XB and YB."),
    0o700646: ("DYS", "Load the Y-coordinate buffer and display the point specified by the XB and YB."),
    # 0o700701: ("DSF", "Skip if display flag =1."),  # duplicated
    0o700702: ("DCF", "Clear display flag."),
    0o700706: ("DLB", "Load the brightness register from AC15-17."),
    # Precision Incremental Display
    0o700501: ("IDVE", "Skip on vertical edge violation."),
    0o700601: ("IDSI", "Skip on stop interrupt."),
    0o700701: ("IDSP", "Skip if light pen flag is set."),
    # 0o701001: ("IDHE", "Skip on horizontal edge violation."),  # duplicated
    0o700504: ("IDRS", "Continue display."),
    0o700512: ("IDRA", "Read display address."),
    0o700606: ("IDLA", "Load address and select."),
    0o700614: ("IDRD", "Restart display."),
    0o700704: ("IDCF", "Clear display control."),
    0o700712: ("IDRC", "Read X and Y coordinates."),
    # Symbol Generator
    0o700641: ("GCL", "Clear done flag (also done by GPL or GPR)."),
    0o701001: ("GSF", "Skip on done."),
    0o701002: ("GPL", "Generator plot left."),
    0o701004: ("GLF", "Load format (bit 15 for space, bits 16 and 17 for size)."),
    0o701042: ("GPR", "Generator plot right."),
    # 0o701084: ("GSP", "Plot a space."), documentation error
    # General Purpose Multiplexer Control
    0o701103: ("ADSM", "Select MX channel."),
    0o701201: ("ADIM", "Increment channel address."),
    # Analog-to-Digital Converters
    0o701301: ("ADSF", "Skip if converter flag is set."),
    0o701304: ("ADSC", "Select and convert."),
    0o701312: ("ADRB", "Read converter buffer."),
    # Relay Buffer
    0o702101: ("ORC", "Clear output relay buffer flip-flop register."),
    0o702104: ("ORS", "Set output relay buffer flip-flop register to correspond with the contents of the accumulator."),
    # Inter Processor Buffer
    0o702201: ("IPSI", "Skip on IPB information flag."),
    0o702212: ("IPRB", "Read IPB buffer."),
    0o702024: ("IPLB", "Load IPB buffer."),
    0o702301: ("IPSA", "Skip on IPB available."),
    0o702302: ("IPDA", "Disable IPB available."),
    0o702304: ("IPEA", "Enable IPB available."),
    # Incremental Plotter and Control
    0o702401: ("PLSF", "Skip if plotter flag is a 1."),
    0o702402: ("PLCF", "Clear plotter flag."),
    0o702404: ("PLPU", "Plotter pen up."),
    0o702501: ("PLPR", "Plotter pen right."),
    0o702502: ("PLDU", "Plotter drum (paper) upward."),
    0o702504: ("PLDD", "Plotter drum (paper) downward."),
    0o702601: ("PLPL", "Plotter pen left."),
    0o702602: ("PLUD", "Plotter drum (paper) upward."),
    0o702604: ("PLPD", "Plotter pen down."),
    # Data Control
    0o704001: ("STC", "Skip on transfer complete."),
    0o704006: ("LWC", "Load word count."),
    0o704101: ("SEC", "Skip on error condition."),
    0o704106: ("LAR", "Load address register."),
    0o704201: ("CDC", "Clear data control."),
    0o704205: ("LCW", "Load control word."),
    0o704212: ("RWC", "Read word count."),
    # Automatic Priority Interrupt
    0o705501: ("CAC", "Clear all channels."),
    0o705502: ("ASC", "Enable selected channel(s)."),
    0o705604: ("DSC", "Disable selected channel(s)."),
    0o700044: ("EPI", "Enable automatic priority interrupt system."),
    0o700004: ("DPI", "Disable automatic priority interrupt system."),
    0o705504: ("ISC", "Initiate break on selected channel (for maintenance purposes)."),
    0o705601: ("DBR", "Debreak."),
    # Serial Drum
    0o706006: ("DRLR", "Load counter and read."),
    0o706046: ("DRLW", "Load counter and write."),
    0o706101: ("DRSF", "Skip if drum transfer flag is set."),
    0o706102: ("DRCF", "Clear drum transfer and error flags."),
    0o706106: ("DRSS", "Load sector and select."),
    0o706201: ("DRSN", "Skip if drum error flag is not set."),
    0o706204: ("DRCS", "Continue select."),
    # Card Punch
    0o706401: ("CPSF", "Skip if card reader flag is set."),
    0o706406: ("CPLR", "Load the punch buffer, clear punch flag."),
    0o706442: ("CPCF", "Clear the card row flag."),
    0o706444: ("CPSE", "Select the card punch."),
    # Automatic Line Printer
    0o706501: ("LPSF", "Skip if printing done flag = 1."),
    0o706502: ("LPCF", "Clear printing done flag."),
    0o706562: ("LPL1", "Load one character into printing buffer."),
    0o706522: ("LPL2", "Load two characters into printing buffer."),
    0o706542: ("LPLD", "Load printing buffer (three characters)."),
    0o706506: ("LPSE", "Select printer and print."),
    0o706601: ("LSSF", "Skip if spacing flag = 1."),
    0o706602: ("LSCF", "Clear spacing flag."),
    0o706604: ("LSLS", "Load spacing buffer and space."),
    # Card Readers
    0o706701: ("CRSF", "Skip if the card reader flag is set."),
    0o706704: ("CRSA", "Select and read a card in alphanumeric mode."),
    0o706712: ("CRRB", "Read the card reader buffer."),
    0o706744: ("CRSB", "Select and read a card in binary mode."),
    # Automatic Magnetic Tape Control
    0o707001: ("MSCR", "Skip if the tape control is ready (TCR=1)."),
    0o707101: ("MSUR", "Skip if the tape unit is ready (TTR)."),
    0o707401: ("*MCC", "Clear CA and WC."),
    0o707405: ("MCA", "Clear CA and WC, and transfer the content of AC5-17 into the CA."),
    0o707402: ("MWC", "Load WC."),
    0o707414: ("MRCA", "Transfer the content of the CA into AC5-17."),
    0o707042: ("MCD", "Disable TCR and clear CR."),
    0o707006: ("MTS", "Clear control register (CR) and clear job done, WCO, and EOR flags."),
    0o707106: ("MTC", "Transmit tape command and start."),
    0o707152: ("MNC", "End continuous mode."),
    0o707204: ("MRD", "Switch mode from read to read/compare."),
    0o707244: ("MRCR", "Switch from read/compare to read."),
    0o707301: ("MSEF", "Skip if EOR flag is set."),
    0o707302: ("*MDEF", "Disable EOR flag."),
    0o707322: ("*MCEF", "Clear EOR flag."),
    0o707342: ("*MEEF", "Enable EOR flag."),
    0o707362: ("MIEF", "Initialize EOR flag."),
    0o707201: ("MSWF", "Skip if WCO flag is set."),
    0o707202: ("*MDWF", "Disable WCO flag."),
    0o707222: ("*MCWF", "Clear WCO flag."),
    0o707242: ("*MEWF", "Enable WCO flag."),
    0o707262: ("MIWF", "Initialize WCO flag."),
    0o707314: ("MTRS", "Read tape status."),
    # DECtape System
    0o707512: ("MMRD", "Read."),
    0o707504: ("MMWR", "Write."),
    0o707644: ("MMSE", "Select."),
    0o707604: ("MMLC", "Load control."),
    0o707612: ("MMRS", "Read status."),
    0o707501: ("MMDF", "Skip on DECtape data flag."),
    0o707601: ("MMBF", "Skip on DECtape block end flag."),
    0o707541: ("MMEF", "Skip on DECtape error flag."),
    # Memory Extension Control
    0o707701: ("SEM", "Skip if in extend mode."),
    0o707702: ("EEM", "Enter extend mode."),
    0o707704: ("LEM", "Leave extend mode."),
    0o707742: ("EMIR", "Extend mode interrupt restore."),
    # Operate Instructions
    # 0o740000: ("OPR or NOP", "Operate group or no operation."),
    0o740000: ("NOP", "Operate group or no operation."),
    0o740001: ("CMA", "Complement accumulator."),
    0o740002: ("CML", "Complement link."),
    0o740004: ("OAS", "Inclusive OR ACCUMULATOR switches."),
    0o740010: ("RAL", "Rotate accumulator left."),
    0o740020: ("RLR", "Rotate accumulator right."),
    0o740040: ("HLT", "Halt."),
    0o740100: ("SMA", "Skip on minus accumulator."),
    0o740200: ("SZA", "Skip on zero accumulator."),
    0o740400: ("SNL", "Skip on non-zero link."),
    0o741000: ("SKP", "Skip."),
    0o741100: ("SPA", "Skip on positive accumulator."),
    0o741200: ("SNA", "Skip on non-zero accumulator."),
    0o741400: ("SZL", "Skip on zero link."),
    0o742010: ("RTL", "Rotate two left."),
    0o742020: ("RTR", "Rotate two right."),
    0o744000: ("CLL", "Clear link."),
    0o744002: ("STL", "Set link."),
    0o744010: ("RCL", "Clear link, then rotate left."),
    0o744020: ("RCR", "Clear link, then rotate right."),
    0o750000: ("CLA", "Clear accumulator."),
    0o750001: ("CLC", "Clear and complement accumulator."),
    0o750004: ("LAS", "Load accumulator from switches."),
    0o750010: ("GLK", "Get link."),
    # 0o76XXXX: ("LAW N", "Load the AC with LAW N."),
}


@dataclass
class Instruction:
    address: int  # Address of the instruction in memory
    word: int  # The 18-bit instruction word
    mnemonic: str  # Mnemonic of the instruction
    comment: str  # Ddescription of the instruction
    reference: t.Optional[int] = None  # Optional reference address (for jumps, calls, etc.)

    def __str__(self) -> str:
        mnemonic = f"{self.mnemonic} {self.reference:o}" if self.reference is not None else self.mnemonic
        return f"{mnemonic:<20s} /{self.word:06o} {self.comment}".strip()


def disassemble_pdp7(words: t.List[int], base_address: int, starting_addres: t.Optional[int] = None) -> bytes:
    instructions: t.List[Instruction] = []
    addresses: t.Set[int] = set()
    if starting_addres is not None:
        addresses.add(starting_addres)
    sub_addresses: t.Set[int] = set()
    sub_exit: t.Set[int] = set()
    lines = []
    for address, word in enumerate(words, start=base_address):
        instruction = disassemble_single_instruction(address, word)
        instructions.append(instruction)
        if instruction.reference is not None:
            addresses.add(instruction.reference)
            if instruction.mnemonic.startswith("JMS") and instruction.reference >= base_address:
                sub_addresses.add(instruction.reference)
            if instruction.mnemonic.startswith("JMP I") and instruction.reference >= base_address:
                sub_exit.add(instruction.reference)
    # Identify subroutines and label them
    sub_addresses = set.intersection(sub_addresses, sub_exit)
    subroutines = {x: f"SUB{i}" for i, x in enumerate(sorted(sub_addresses), start=1)}
    for instruction in instructions:
        # Subroutine entry/exit comments
        if instruction.address in subroutines:
            instruction.comment = "Entry to subroutine."
            lines.append("")
            lines.append(f"{subroutines[instruction.address]},")
        elif instruction.mnemonic.startswith("JMP I") and instruction.reference in subroutines:
            instruction.comment = f"Exit from subroutine {subroutines[instruction.reference]}."
        prefix = f"{instruction.address:o}/" if instruction.address in addresses else ""
        if instruction.reference is None:
            mnemonic = instruction.mnemonic
        elif instruction.reference in subroutines:
            mnemonic = f"{instruction.mnemonic} {subroutines[instruction.reference]}"
        else:
            mnemonic = f"{instruction.mnemonic} {instruction.reference:o}"
        lines.append(f"{prefix:<12s} {mnemonic:<20s} /{instruction.word:06o} {instruction.comment}".rstrip())
    return "\n".join(lines).encode('ascii')


def disassemble_single_instruction(address: int, word: int) -> Instruction:
    """
    Disassembles a single 18-bit PDP-7 instruction word.
    """
    if not 0 <= word < 2**18:
        raise ValueError("Instruction word must be a valid 18-bit integer")

    mnemonic, comment = OPCODES.get(word, (None, None))
    if mnemonic is not None:
        return Instruction(address=address, word=word, mnemonic=mnemonic, comment=comment)  # type: ignore

    opcode = (word >> 12) & ~1

    # Handle Group 1 Operate Instructions
    if opcode == GROUP1_OP:
        bits = [int(digit) for digit in f"{word:018b}"]
        tmp = []

        if bits[8]:
            if bits[9]:
                tmp.append("SZL")
            if bits[10]:
                tmp.append("SNA")
            if bits[11]:
                tmp.append("SPA")
        else:
            if bits[9]:
                tmp.append("SNL")
            if bits[10]:
                tmp.append("SZA")
            if bits[11]:
                tmp.append("SMA")

        if bits[12]:
            tmp.append("HLT")
        if bits[7]:
            if bits[13]:
                tmp.append("RTR")
            if bits[14]:
                tmp.append("RTL")
        else:
            if bits[13]:
                tmp.append("RAR")
            if bits[14]:
                tmp.append("RAL")

        if bits[5]:
            tmp.append("CLA")
        if bits[6]:
            tmp.append("CLL")

        if bits[15]:
            tmp.append("OAS")
        if bits[16]:
            tmp.append("CML")
        if bits[17]:
            tmp.append("CMA")
        mnemonic = " ".join(tmp)
        return Instruction(address=address, word=word, mnemonic=mnemonic[0], comment="Operate group", reference=None)
    elif opcode == GROUP2_OP:
        mnemonic = "LAW"
        comment = "Load the AC with LAW N."
    else:
        is_indirect = ' I' if ((word >> 13) & 0o1) else ''
        mnemonic, comment = OPCODES.get(opcode & ~2, (None, None))
        if mnemonic and is_indirect:
            mnemonic = f"{mnemonic}{is_indirect}"
    if mnemonic is None:
        mnemonic = "IOT"
    reference: t.Optional[int] = word & 0o17777
    if mnemonic in ("CAL", "CAL I"):  # The address portion of this instruction is ignored.
        reference = None
    if not comment:
        comment = ""
    return Instruction(address=address, word=word, mnemonic=mnemonic, comment=comment, reference=reference)
