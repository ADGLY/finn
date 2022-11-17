# Copyright (c) 2020, Xilinx
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of FINN nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
from qonnx.core.datatype import DataType

from finn.custom_op.fpgadataflow.hlscustomop import HLSCustomOp

"""@package thresholding_binary_search
- ONNX i/o tensor shape assumptions for Thresholding:
- input 0 is the input tensor, shape (..., NumChannels)
- input 1 is the threshold tensor, shape (NumChannels, n_thres)
- output 0 is the output tensor, shape (..., NumChannels) - same as input
- the '...' here can be any shape (representing groups of vectors)

This module creates an RTL IP, HLS is not supported. See 'thresholding_batch'
for a HLS equivalent.
"""


class Thresholding_Bin_Search(HLSCustomOp):
    """Class that corresponds to finn-rtllib 'thresholding' function."""

    def __init__(self, onnx_node):
        super().__init__(onnx_node)

    def get_nodeattr_types(self):
        my_attrs = {
            # parallelization; channels thresholded per cycle
            "PE": ("i", True, 0),
            # number of channels (each may have different thresholds)
            "NumChannels": ("i", True, 0),
            # number of steps in thresholding function. Used only in decoupled mode
            "numSteps": ("i", True, 1),
            # string defining memory type
            "ram_style": ("s", False, "distributed", {"distributed", "block"}),
            # FINN DataTypes for inputs, outputs
            "inputDataType": ("s", True, ""),
            "weightDataType": ("s", True, ""),
            "outputDataType": ("s", True, ""),
            # input and output FIFO depths
            "inFIFODepth": ("i", False, 0),
            "outFIFODepth": ("i", False, 0),
            # number of input vectors, examples:
            # [1] is a single vector (like a FC layer with batch=1)
            # [4] is four vectors (like a FC layer with batch=4)
            # [1, 4, 4] is four * four vectors (like a conv layer with batch=1)
            "numInputVectors": ("ints", False, [1]),
            # memory mode for the thresholds
            # const -- embedded thresholds, default
            # decoupled -- streaming thresholds with streamer packaged inside IP
            "mem_mode": ("s", False, "const", {"const", "decoupled"}),
            # (mem_mode = decoupled only) whether weights (thresholds) will be
            # writable through an AXI-lite interface during runtime
            # 1 for enabled, 0 for disabled.
            # see finn-rtllib/memstream/doc/README for more about the memory
            # address map used for writable weights
            # IMPORTANT: After using AXI lite to either read or write the weights,
            # always "flush" the accelerator by first passing a dummy input
            # vector through the accelerator. This will get rid of any old
            # weight data from the weight FIFOs.
            "runtime_writeable_weights": ("i", False, 0, {0, 1}),
            "gen_top_module": ("s", False, ""),
            "activation_bias": ("i", False, 0),
        }
        my_attrs.update(super().get_nodeattr_types())
        return my_attrs

    def calc_tmem(self):
        num_channels = self.get_nodeattr("NumChannels")
        pe = self.get_nodeattr("PE")
        return num_channels // pe

    def make_shape_compatible_op(self, model):
        return []

    def infer_node_datatype(self, model):
        return

    def verify_node(self):
        return []

    def bram_estimation(self):
        return 0

    def lut_estimation(self):
        return 0

    def get_input_datatype(self):
        return DataType[self.get_nodeattr("inputDataType")]

    def get_output_datatype(self):
        return DataType[self.get_nodeattr("outputDataType")]

    def get_weight_datatype(self):
        """The term 'weights' and 'thresholds' are used interchangably in this class."""
        return DataType[self.get_nodeattr("weightDataType")]

    def minimize_accumulator_width(self, model):
        return None

    def get_instream_width(self):
        i_bits = self.get_input_datatype().bitwidth()
        return i_bits * self.get_nodeattr("PE")

    def get_outstream_width(self):
        o_bits = self.get_output_datatype().bitwidth()
        return o_bits * self.get_nodeattr("PE")

    def get_weightstream_width(self):
        # Only 'decoupled' mode is supported
        mem_mode = self.get_nodeattr("mem_mode")
        if mem_mode != "decoupled": raise Exception("Unrecognized memory mode for this node: {}".format(mem_mode))
        pe = self.get_nodeattr("PE")
        wp = self.get_weight_datatype().bitwidth()
        n_thres_steps = self.get_nodeattr("numSteps")
        w_width = pe * wp * n_thres_steps
        return w_width

    def get_folded_input_shape(self):
        fold = self.calc_tmem()
        pe = self.get_nodeattr("PE")
        vecs = list(self.get_nodeattr("numInputVectors"))
        folded_input_shape = tuple(vecs + [fold, pe])
        return folded_input_shape

    def get_folded_output_shape(self):
        # same shape as input
        return self.get_folded_input_shape()

    def get_normal_input_shape(self):
        num_channels = self.get_nodeattr("NumChannels")
        vecs = list(self.get_nodeattr("numInputVectors"))
        normal_input_shape = tuple(vecs + [num_channels])
        return normal_input_shape

    def get_normal_output_shape(self):
        # same shape as input
        return self.get_normal_input_shape()

    def get_number_output_values(self):
        return 0

    def get_exp_cycles(self):
        return 0

    def get_template_param_values(self):
        return dict()

    def make_weight_file(self, weights, weight_file_mode, weight_file_name):
        """Produce a file containing given weights (thresholds) in appropriate
        format for this layer. This file can be used for either synthesis or
        run-time reconfig of weights.

        Arguments:
        * weights : numpy array with weights to be put into the file
        * weight_file_mode : one of {hls_header, decoupled_verilog_dat,
          decoupled_runtime}
        * weight_file_name : filename for the weight file to be generated
        """
        return

    # Get the integer from the DataType and string-ify it
    # This assumes that the data is in the form "INTx" or similar
    def conv_datatype_to_str(self, data_type):
        # Handle the case that an int is passed to the function
        if isinstance(data_type, int):
            return str(data_type)
        return str(DataType[data_type].bitwidth())

    def prepare_codegen_rtl_values(self):
        """All dictionary values produced in this function are to replace
        their key value(s) in the RTL template files"""
        code_gen_dict = {}

        # Identify the module names
        code_gen_dict["$MODULE_NAME$"] = [self.get_verilog_top_module_name()]
        code_gen_dict["$MODULE_NAME_AXI$"] = [self.get_verilog_top_module_name() + "_axi"]
        code_gen_dict["$MODULE_NAME_AXI_WRAPPER$"] = [self.get_verilog_top_module_name() + "_axi_wrapper"]
        # Set the top module name - AXI wrapper
        code_gen_dict["$TOP_MODULE$"] = code_gen_dict["$MODULE_NAME_AXI_WRAPPER$"]

        # Identify the module variables
        output_data_type = self.get_nodeattr("outputDataType") # output precision
        input_data_type = self.get_nodeattr("inputDataType") # input/threshold precision
        num_channels = self.get_nodeattr("NumChannels") # number of channels
        bias = self.get_nodeattr("activation_bias") # activation bias value

        code_gen_dict["$N$"] = [self.conv_datatype_to_str(output_data_type)] # output precision
        code_gen_dict["$M$"] = [self.conv_datatype_to_str(input_data_type)] # input/threshold precision
        code_gen_dict["$C$"] = [self.conv_datatype_to_str(num_channels)] # number of channels
        code_gen_dict["$BIAS$"] = [self.conv_datatype_to_str(bias)] # activation bias value

        # Is the input datatype signed or unsigned? The thresholding core needs to know this
        if self.get_input_datatype().min() < 0:
            code_gen_dict["$SIGN$"] = ["signed"]
        else:
            code_gen_dict["$SIGN$"] = ["unsigned"]

        return code_gen_dict

    def get_rtl_file_list(self):
        return ["thresholding.sv",
                "thresholding_axi.sv",
                "thresholding_axi_wrapper.v"]

    def get_rtl_file_paths(self):
        rtl_root_dir = os.environ["FINN_ROOT"] + "/finn-rtllib/thresholding/hdl/"
        rtl_file_list = self.get_rtl_file_list()
        rtl_file_paths = [rtl_root_dir + file for file in rtl_file_list]
        return rtl_file_paths

    def get_rtl_template_data(self, path):
        with open(path, "r") as f:
            template = f.read()
        return template

    def fill_in_rtl_template_data(self, replace_dict, template_data):
        template_data_cp = template_data
        for key in replace_dict:
            replacement_line = "\n".join(replace_dict[key])
            template_data_cp = template_data_cp.replace(key, replacement_line)
        return template_data_cp

    def dump_rtl_data(self, dest_dir, filename, data):
        with open(os.path.join(dest_dir, filename), "w") as f:
            f.write(data)
        return

    def generate_hdl(self):
        # Generate a dictionary of values to put in RTL template
        code_gen_dict = self.prepare_codegen_rtl_values()

        # Retrieve the destination directory for the final RTL files
        code_gen_dir = self.get_nodeattr("code_gen_dir_ipgen")

        for rtl_file_path in self.get_rtl_file_paths():
            # read in original RTL template file
            template_data = self.get_rtl_template_data(rtl_file_path)
            # apply code generation to templates
            data = self.fill_in_rtl_template_data(code_gen_dict, template_data)
            # dump filled-in template to destination directory for compilation
            file_only_path = rtl_file_path.split('/')[-1]
            self.dump_rtl_data(code_gen_dir, file_only_path, data)

        # Before we return - set the 'gen_top_module' attribute for use later by PyVerilator and IPI generation
        self.set_nodeattr("gen_top_module", code_gen_dict["$TOP_MODULE$"][0])
        return

    def code_generation_ipgen(self, model, fpgapart, clk):
        self.generate_hdl()

        # set ipgen_path and ip_path so that HLS-Synth transformation
        # and stich_ip transformation do not complain
        # i.e. during the HLSSynthIP() transformation
        code_gen_dir = self.get_nodeattr("code_gen_dir_ipgen")
        self.set_nodeattr("ipgen_path", code_gen_dir)
        self.set_nodeattr("ip_path", code_gen_dir)

    def generate_params(self, model, path):
        return

    def execute_node(self, context, graph):
        return

    def code_generation_ipi(self):
        """Constructs and returns the TCL commands for node instantiation as an RTL block."""
        cmd = []
        rtl_file_list = self.get_rtl_file_list()
        code_gen_dir = self.get_nodeattr("code_gen_dir_ipgen")

        for rtl_file in rtl_file_list:
            cmd.append("add_files -norecurse %s"
            % (
                os.path.join(
                    code_gen_dir, rtl_file
                )
            ))

        # Create an RTL block, not an IP core (-type ip)
        cmd.append("create_bd_cell -type module -reference %s %s"
            % (self.get_nodeattr("gen_top_module"), self.onnx_node.name))

        # ERROR: [BD 41-237] Bus Interface property FREQ_HZ does not match between
        # /Thresholding_Binary_Search_0/s_axis(100000000 and /StreamingFIFO_0/out_V(200000000.000000)
        cmd.append("set_property -dict [list CONFIG.FREQ_HZ {200000000}] [get_bd_intf_pins Thresholding_Binary_Search_0/s_axis]")

        # ERROR: [BD 41-237] Bus Interface property FREQ_HZ does not match between
        # /StreamingFIFO_1/in0_V(200000000.000000) and /Thresholding_Binary_Search_0/m_axis(100000000)
        cmd.append("set_property -dict [list CONFIG.FREQ_HZ {200000000}] [get_bd_intf_pins Thresholding_Binary_Search_0/m_axis]")

        return cmd

    def get_verilog_top_module_intf_names(self):
        """Return a dict of names of input and output interfaces.
        The keys reflect the protocols each interface implements:
        'clk', 'rst', 'm_axis', 's_axis', 'aximm', 'axilite'.
        Values are lists of tuples (axis, aximm) or names (axilite):
        'axis' tuples correspond to the list of node inputs in order,
        each tuple is (interface_name, interface_width_bits).
        axilite always assumed to be 32 bits and is not tuple (name only).
        Each block must have at most one aximm and one axilite."""

        intf_names = super().get_verilog_top_module_intf_names()
        # Only 'decoupled' mode is supported - check before adding axilite interface
        mem_mode = self.get_nodeattr("mem_mode")
        if mem_mode != "decoupled": raise Exception("Unrecognized memory mode for this node: {}".format(mem_mode))
        intf_names["axilite"] = ["s_axilite"]
        intf_names["s_axis"] = [["s_axis"]]
        intf_names["m_axis"] = [["m_axis"]]

        self.set_nodeattr("runtime_writeable_weights", 1)

        return intf_names

    def find_next_power_of_2(self, n):
        # Negative values will loop infinitely below - return 0
        if n <= 0:
            return 0
        # If '1' is requested, output will be '0' in the loop below, so avoid this earlier.
        elif n == 1:
            return 2 # i.e. 2**1

        # decrement 'n' (to handle cases when `n` itself is a power of 2)
        n = n - 1

        # loop until only one bit is left
        while n & n - 1:
            # unset rightmost bit
            n = n & n - 1
        return n << 1

    def twos_comp(self, val, bitwidth):
        return (val + (1 << bitwidth)) % (1 << bitwidth)

    def prep_axilite_val(self, val):
        return self.twos_comp(int(val), self.get_weight_datatype().bitwidth())

    def get_dynamic_config(self, model, address_stride=1):
        ## TODO - not sure this description is correct
        """Returns a configuration dictionary containing axilite write commands
        in order to program the thresholds into the RTL core during runtime.
        The default address stride for the weights is 1 byte."""

        thresholds = model.get_initializer(self.onnx_node.input[1])
        num_channels, num_weights_per_channel = thresholds.shape

        weight_addr_boundary = self.find_next_power_of_2(num_weights_per_channel)
        # Make sure that the next power of 2 (output) is greater than the input
        assert weight_addr_boundary >= num_weights_per_channel

        config = {}
        channel_cntr = 0
        for channel in thresholds:
            channel_start_addr = (channel_cntr * weight_addr_boundary * address_stride)
            weight_cntr = 0
            addr = 0
            for weight in channel:
                key_name = "{}_{}{}_{}{}".format("axilite", "ch", str(channel_cntr), "w", str(weight_cntr))
                config[key_name] = (channel_start_addr + addr, self.prep_axilite_val(weight))

                weight_cntr += 1
                addr += address_stride

            channel_cntr += 1

        return config

    def global_includes(self):
        pass

    def defines(self, var):
        pass

    def read_npy_data(self):
        pass

    def strm_decl(self):
        pass

    def docompute(self):
        pass

    def dataoutstrm(self):
        pass

    def save_as_npy(self):
        pass

    def blackboxfunction(self):
        pass

    def pragmas(self):
        pass
