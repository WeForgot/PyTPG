import random
import numpy as np
from numba import njit
import math
from tpg.utils import flip

"""
A program that is executed to help obtain the bid for a learner.
"""
class Program:

    """
    bits for:
    mode   op    dest       src
    1      1111   111...   11111111111...
    Mode: Always 1 bit, whether to use register or obs for input.
    Op: Now 4 bits, one of 8 math operations (add, sub, mult, div, cos, log,
        exp, neg) + memory read/write.
    Dest: At-least # of bits to store # of registers. The register to place the
        result of the instruction into.
    Src: At-least # of bits to store size of input. The index to take from
        input, or a register depending on Mode.
    """
    instructionLengths = [1,4,3,23]

    idCount = 0 # unique id of each program

    def __init__(self, instructions=None, maxProgramLength=128):
        if instructions is not None: # copy from existing
            self.instructions = list(instructions)
        else: # create random new
            maxInst = 2**sum(Program.instructionLengths)-1
            self.instructions = [random.randint(0, maxInst) for _ in
                            range(random.randint(1, maxProgramLength))]

        self.id = Program.idCount
        Program.idCount += 1

        self.update()


    """
    Executes the program which returns a single final value.
    """
    @njit
    def execute(inpt, regs, modes, ops, dsts, srcs, memMatrix, memRows, memCols):
        regSize = len(regs)
        inptLen = len(inpt)
        for i in range(len(modes)):
            # first get source
            if modes[i] == False:
                src = regs[srcs[i]%regSize]
            else:
                src = inpt[srcs[i]%inptLen]

            # do operation
            op = ops[i]
            x = regs[dsts[i]]
            y = src
            dest = dsts[i]%regSize

            if op == 0 or op == 10:
                regs[dest] = x+y
            elif op == 1 or op == 11:
                regs[dest] = x-y
            elif op == 2 or op == 12:
                regs[dest] = x*y
            elif op == 3 or op == 13:
                if y != 0:
                    regs[dest] = x/y
            elif op == 4 or op == 14:
                regs[dest] = math.cos(y)
            elif op == 5 or op == 15:
                if y > 0:
                    regs[dest] = math.log(y)
            elif op == 6:
                regs[dest] = math.exp(y)
            elif op == 7:
                if x < y:
                    regs[dest] = x*(-1)
            elif op == 8: # read from memory
                index = srcs[i]
                index %= (memRows*memCols)
                row = int(index / memRows)
                col = index % memCols

                regs[dest] = memMatrix[row, col]
            elif op == 9: # write to memory
                # row offset (start from center, go to edges)
                for i in range(int(memRows/2)):
                    # probability to write (gets smaller as i increases)
                    # need to modify to be more robust with different # of rows
                    writeProb = 0.25 - (0.01*i)**2
                    # column to maybe write corresponding value into
                    for col in range(memCols):
                        # try write to lower half
                        if np.random.rand(1)[0] < writeProb:
                            row = (int(memRows/2) - i) - 1
                            memMatrix[row,col] = regs[col]
                        # try write to upper half
                        if np.random.rand(1)[0] < writeProb:
                            row = int(memRows/2) + i
                            memMatrix[row,col] = regs[col]

            if math.isnan(regs[dest]):
                regs[dest] = 0
            elif regs[dest] == np.inf:
                regs[dest] = np.finfo(np.float64).max
            elif regs[dest] == np.NINF:
                regs[dest] = np.finfo(np.float64).min

    """
    Takes instructions and converts them into np arrays for easier more
    efficient execution.
    """
    def update(self):
        totalLen = sum(Program.instructionLengths)
        instsData = np.array([
            [
                getIntSegment(inst, 0, Program.instructionLengths[0], totalLen),
                getIntSegment(inst, Program.instructionLengths[0],
                        Program.instructionLengths[1], totalLen),
                getIntSegment(inst, sum(Program.instructionLengths[:2]),
                        Program.instructionLengths[2], totalLen),
                getIntSegment(inst, sum(Program.instructionLengths[:3]),
                        Program.instructionLengths[3], totalLen)
            ]
            for inst in self.instructions])

        self.modes = np.array(instsData[:,0], dtype = bool)
        self.operations = np.array(instsData[:,1], dtype = np.int8)
        self.destinations = np.array(instsData[:,2], dtype = np.int8)
        self.sources = np.array(instsData[:,3], dtype = np.int32)


    """
    Mutates the program, by performing some operations on the instructions. If
    inpts, and outs (parallel) not None, then mutates until this program is
    distinct. If update then calls update when done.
    """
    def mutate(self, pMutRep, pDelInst, pAddInst, pSwpInst, pMutInst,
                regSize, uniqueProgThresh, inputs=None, outputs=None, update=True,
                maxMuts=100):
        if inputs is not None and outputs is not None:
            # mutate until distinct from others
            unique = False
            while not unique:
                if maxMuts <= 0:
                    break # too much
                maxMuts -= 1

                unique = True # assume unique until shown not
                self.mutateInstructions(pDelInst, pAddInst, pSwpInst, pMutInst)
                self.update()
                # check unique on all inputs from all learners outputs
                # input and outputs of i'th learner
                for i, lrnrInputs in enumerate(inputs):
                    lrnrOutputs = outputs[i]

                    for j, input in enumerate(lrnrInputs):
                        output = lrnrOutputs[j]
                        regs = np.zeros(regSize)
                        Program.execute(input, regs, self.modes, self.operations,
                                        self.destinations, self.sources)
                        myOut = regs[0]
                        if abs(output-myOut) < uniqueProgThresh:
                            unique = False
                            break

                    if unique == False:
                        break
        else:
            # mutations repeatedly, random amount
            mutated = False
            while not mutated or flip(pMutRep):
                self.mutateInstructions(pDelInst, pAddInst, pSwpInst, pMutInst)
                mutated = True

        if update:
            self.update()

    """
    Potentially modifies the instructions in a few ways.
    """
    def mutateInstructions(self, pDel, pAdd, pSwp, pMut):
        changed = False

        while not changed:
            # maybe delete instruction
            if len(self.instructions) > 1 and flip(pDel):
                del self.instructions[random.randint(0, len(self.instructions)-1)]
                changed = True

            # maybe mutate an instruction (flip a bit)
            if flip(pMut):
                idx = random.randint(0, len(self.instructions)-1)
                num = self.instructions[idx]
                totalLen = sum(Program.instructionLengths)
                bit = random.randint(0, totalLen-1)
                self.instructions[idx] = bitFlip(num, bit, totalLen)
                changed = True

            # maybe swap two instructions
            if len(self.instructions) > 1 and flip(pSwp):
                # indices to swap
                idx1, idx2 = random.sample(range(len(self.instructions)), 2)
                # do swap
                tmp = self.instructions[idx1]
                self.instructions[idx1] = self.instructions[idx2]
                self.instructions[idx2] = tmp
                changed = True

            # maybe add instruction
            if flip(pAdd):
                maxInst = 2**sum(Program.instructionLengths)-1
                self.instructions.insert(
                            random.randint(0, len(self.instructions)-1),
                            random.randint(0, maxInst))
                changed = True

"""
Takes an int and returns another int made of some bits of the original.
"""
def getIntSegment(num, bitStart, bitLen, totalLen):
    binStr = format(num, 'b').zfill(totalLen)
    return int(binStr[bitStart:bitStart+bitLen], 2)

"""
Flip a bit in the provided int.
"""
def bitFlip(num, bit, totalLen):
    binStr = format(num, 'b').zfill(totalLen)

    if binStr[bit] == '0':
        newNum = int(binStr[:bit] + '1' + binStr[bit+1:], 2)
    else:
        newNum = int(binStr[:bit] + '0' + binStr[bit+1:], 2)

    return newNum
