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

import numpy as np
import os
import qonnx
import shutil
import warnings
from qonnx.core.modelwrapper import ModelWrapper
from qonnx.custom_op.registry import getCustomOp
from qonnx.transformation.base import Transformation
from qonnx.util.basic import gen_finn_dt_tensor, roundup_to_integer_multiple

import finn.util
import finn.util.data_packing as dpk
from finn.util.basic import make_build_dir
from finn.util.data_packing import (
    hexstring2npbytearray,
    pack_innermost_dim_as_hex_string,
)

from . import template_driver


def to_external_tensor(init, w_dtype):
    """Return an appropriately formatted and packed numpy byte array for given
    external parameter tensor."""

    weight_width = init.shape[1] * w_dtype.bitwidth()
    weight_width_padded = roundup_to_integer_multiple(weight_width, 4)
    hex_init = pack_innermost_dim_as_hex_string(init, w_dtype, weight_width_padded, prefix="0x")
    ext_weight = np.array([], dtype=np.uint8)
    for line in hex_init:
        array_line = [x for x in reversed(hexstring2npbytearray(line, remove_prefix="0x"))]
        ext_weight = np.append(ext_weight, array_line)

    return ext_weight


class MakePYNQDriver(Transformation):
    """Create PYNQ Python code to correctly interface the generated
    accelerator, including data packing/unpacking. Should be called
    after conversion to HLS layers, folding and the creation of
    dataflow partitions for correct operation.

    platform: one of ["zynq-iodma", "alveo"]

    Outcome if successful: sets the pynq_driver_dir attribute in the ONNX
    ModelProto's metadata_props field, with the created driver dir as the
    value. If any layers use runtime-writable parameters, those will be gathered
    under the runtime_weights/ subfolder of the pynq_driver_dir.
    """

    def __init__(self, platform):
        super().__init__()
        self.platform = platform

    def apply(self, model):
        # create a temporary folder for the generated driver
        pynq_driver_dir = make_build_dir(prefix="pynq_driver_")
        model.set_metadata_prop("pynq_driver_dir", pynq_driver_dir)

        # create the base FINN driver -- same for all accels
        driver_base_template = (
            os.environ["FINN_ROOT"] + "/src/finn/qnn-data/templates/driver/driver_base.py"
        )
        driver_base_py = pynq_driver_dir + "/driver_base.py"
        shutil.copy(driver_base_template, driver_base_py)
        # driver depends on qonnx and finn packages
        # extract individual source files and copy to driver folder
        qonnx_target_path = pynq_driver_dir + "/qonnx"
        finn_target_path = pynq_driver_dir + "/finn"
        os.makedirs(qonnx_target_path + "/core", exist_ok=True)
        os.makedirs(qonnx_target_path + "/util", exist_ok=True)
        os.makedirs(finn_target_path + "/util", exist_ok=True)
        qonnx_path = qonnx.__path__[0]
        finn_util_path = finn.util.__path__[0]
        files_to_copy = []
        files_to_copy.append(
            (qonnx_path + "/core/datatype.py", qonnx_target_path + "/core/datatype.py")
        )
        files_to_copy.append(
            (qonnx_path + "/core/__init__.py", qonnx_target_path + "/core/__init__.py")
        )
        files_to_copy.append((qonnx_path + "/util/basic.py", qonnx_target_path + "/util/basic.py"))
        files_to_copy.append(
            (qonnx_path + "/util/__init__.py", qonnx_target_path + "/util/__init__.py")
        )
        files_to_copy.append(
            (
                finn_util_path + "/data_packing.py",
                finn_target_path + "/util/data_packing.py",
            )
        )
        files_to_copy.append(
            (
                finn_util_path + "/__init__.py",
                finn_target_path + "/util/__init__.py",
            )
        )
        for src_file, target_file in files_to_copy:
            shutil.copy(src_file, target_file)
        # extract input-output shapes from the graph
        # TODO convert this to an analysis pass?
        idt = []
        idma_names = []
        ishape_normal = []
        ishape_folded = []
        ishape_packed = []
        for idma_ind, graph_in in enumerate(model.graph.input):
            i_tensor_name = graph_in.name
            # get inp tensor properties
            i_tensor_dt = model.get_tensor_datatype(i_tensor_name)
            i_tensor_shape_normal = tuple(model.get_tensor_shape(i_tensor_name))
            # go down into dataflow partition to get folded shape info etc
            # TODO consider setting these as attributes during dataflow partitioning
            i_consumer = model.find_consumer(i_tensor_name)
            assert (
                i_consumer.op_type == "StreamingDataflowPartition"
            ), """
                Ensure CreateDataflowPartition called before driver creation."""
            first_df_model = ModelWrapper(getCustomOp(i_consumer).get_nodeattr("model"))
            assert (
                first_df_model.graph.node[0].op_type == "IODMA"
            ), "First partition must hold input IODMA"
            successors = model.find_direct_successors(i_consumer)
            successor_input_num = list(successors[0].input).index(i_consumer.output[0])
            successor_sdp = getCustomOp(successors[0])
            successor_df_model = ModelWrapper(successor_sdp.get_nodeattr("model"))
            first_node = successor_df_model.find_consumer(
                successor_df_model.graph.input[successor_input_num].name
            )
            i_tensor_shape_folded = tuple(getCustomOp(first_node).get_folded_input_shape())
            # generate dummy folded i/o tensors and their packed versions
            i_tensor_dummy_folded = gen_finn_dt_tensor(i_tensor_dt, i_tensor_shape_folded)
            i_tensor_dummy_packed = dpk.finnpy_to_packed_bytearray(
                i_tensor_dummy_folded, i_tensor_dt
            )
            i_tensor_shape_packed = i_tensor_dummy_packed.shape
            # append all input tensor info to relevant lists
            idt.append("DataType['%s']" % i_tensor_dt.name)
            ishape_normal.append(i_tensor_shape_normal)
            ishape_folded.append(i_tensor_shape_folded)
            ishape_packed.append(i_tensor_shape_packed)
            idma_names.append(getCustomOp(i_consumer).get_nodeattr("instance_name"))

        odt = []
        odma_names = []
        oshape_normal = []
        oshape_folded = []
        oshape_packed = []
        for odma_ind, graph_out in enumerate(model.graph.output):
            o_tensor_name = graph_out.name
            # get inp tensor properties
            o_tensor_dt = model.get_tensor_datatype(o_tensor_name)
            o_tensor_shape_normal = tuple(model.get_tensor_shape(o_tensor_name))
            # go down into IODMA partition to get folded shape info etc
            # TODO consider setting these as attributes during dataflow partitioning
            o_producer = model.find_producer(o_tensor_name)
            assert (
                o_producer.op_type == "StreamingDataflowPartition"
            ), """
                Ensure CreateDataflowPartition called before driver creation."""
            df_model = ModelWrapper(getCustomOp(o_producer).get_nodeattr("model"))
            assert df_model.graph.node[-1].op_type == "IODMA", "Partition must hold output IODMA"
            predecessors = model.find_direct_predecessors(o_producer)
            predecessor_output_num = list(predecessors[0].output).index(o_producer.input[0])
            predecessor_sdp = getCustomOp(predecessors[0])
            predecessor_df_model = ModelWrapper(predecessor_sdp.get_nodeattr("model"))
            last_node = predecessor_df_model.find_producer(
                predecessor_df_model.graph.output[predecessor_output_num].name
            )
            o_tensor_shape_folded = tuple(getCustomOp(last_node).get_folded_output_shape())
            o_tensor_dummy_folded = gen_finn_dt_tensor(o_tensor_dt, o_tensor_shape_folded)
            o_tensor_dummy_packed = dpk.finnpy_to_packed_bytearray(
                o_tensor_dummy_folded, o_tensor_dt
            )
            o_tensor_shape_packed = o_tensor_dummy_packed.shape
            # append all output tensor info to relevant lists
            odt.append("DataType['%s']" % o_tensor_dt.name)
            oshape_normal.append(o_tensor_shape_normal)
            oshape_folded.append(o_tensor_shape_folded)
            oshape_packed.append(o_tensor_shape_packed)
            odma_names.append(getCustomOp(o_producer).get_nodeattr("instance_name"))

        # generate external weights npy files
        weights_dir = pynq_driver_dir + "/runtime_weights"

        os.makedirs(weights_dir)
        idma_idx = 0
        ext_weight_dma_cnt = 0

        for node in model.graph.node:
            assert (
                node.op_type == "StreamingDataflowPartition"
            ), "CreateDataflowPartition needs to be applied before driver generation"

            if len(node.input) > 0:
                producer = model.find_producer(node.input[0])
                init_tensor = model.get_initializer(node.input[0])
            else:
                producer = None
                init_tensor = None

            if producer is None:  # input dma?
                sdp_inst = getCustomOp(node)
                idma_name = sdp_inst.get_nodeattr("instance_name")
                df_model = ModelWrapper(sdp_inst.get_nodeattr("model"))
                assert df_model.graph.node[0].op_type == "IODMA"
                iodma_node = getCustomOp(df_model.graph.node[0])
                if iodma_node.get_nodeattr("burstMode") == "wrap":  # input weights dma?
                    init_tensor = df_model.get_initializer(iodma_node.onnx_node.input[0])
                    ext_weight_dma_cnt += 1
                    w_dtype = df_model.get_tensor_datatype(iodma_node.onnx_node.input[0])
                    init_external_tensor = to_external_tensor(init_tensor, w_dtype)
                    np.save(weights_dir + "/" + idma_name + ".npy", init_external_tensor)
                idma_idx += 1

        # fill in the driver template
        driver_py = pynq_driver_dir + "/driver.py"
        driver = template_driver.pynq_driver_template

        driver = driver.replace("$PLATFORM$", self.platform)
        driver = driver.replace("$INPUT_FINN_DATATYPE$", str(idt).replace('"', ""))
        driver = driver.replace("$INPUT_SHAPE_NORMAL$", str(ishape_normal))
        driver = driver.replace("$INPUT_SHAPE_FOLDED$", str(ishape_folded))
        driver = driver.replace("$INPUT_SHAPE_PACKED$", str(ishape_packed))
        driver = driver.replace("$OUTPUT_FINN_DATATYPE$", str(odt).replace('"', ""))
        driver = driver.replace("$OUTPUT_SHAPE_NORMAL$", str(oshape_normal))
        driver = driver.replace("$OUTPUT_SHAPE_FOLDED$", str(oshape_folded))
        driver = driver.replace("$OUTPUT_SHAPE_PACKED$", str(oshape_packed))
        driver = driver.replace("$INPUT_DMA_NAME$", "%s" % str(idma_names))
        driver = driver.replace("$OUTPUT_DMA_NAME$", "%s" % str(odma_names))
        driver = driver.replace("$NUM_INPUTS$", str(len(idma_names)))
        driver = driver.replace("$NUM_OUTPUTS$", str(len(odma_names)))
        driver = driver.replace("$EXT_WEIGHT_NUM$", str(ext_weight_dma_cnt))

        with open(driver_py, "w") as f:
            f.write(driver)

        # add validate.py to run full top-1 test (only for suitable networks)
        validate_py = pynq_driver_dir + "/validate.py"
        validate_template = (
            os.environ["FINN_ROOT"] + "/src/finn/qnn-data/templates/driver/validate.py"
        )
        shutil.copy(validate_template, validate_py)

        # generate weight files for runtime-writable layers

        for sdp_ind, sdp_node in enumerate(model.graph.node):
            assert sdp_node.op_type == "StreamingDataflowPartition"
            # get dataflow model
            sdp_node = getCustomOp(sdp_node)
            dataflow_model_filename = sdp_node.get_nodeattr("model")
            dataflow_model = ModelWrapper(dataflow_model_filename)
            rt_layer_ind = 0
            for node in dataflow_model.graph.node:
                if node.op_type in ["MatrixVectorActivation", "Thresholding_Batch"]:
                    node_inst = getCustomOp(node)
                    is_rt_weights = node_inst.get_nodeattr("runtime_writeable_weights")
                    if is_rt_weights == 1:
                        fcl_w = dataflow_model.get_initializer(node.input[1])
                        w_filename = weights_dir + "/%d_%d_%s.dat" % (
                            sdp_ind,
                            rt_layer_ind,
                            node.name,
                        )
                        node_inst.make_weight_file(fcl_w, "decoupled_runtime", w_filename)
                        rt_layer_ind += 1
                elif node.op_type == "StreamingDataflowPartition":
                    warnings.warn(
                        """Nested StreamingDataflowPartition are not supported
                    """
                    )
                else:
                    continue

        return (model, False)
