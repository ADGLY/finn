# Copyright (c) 2019, Xilinx
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    2. Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#    3. Neither the name of the <organization> nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import numpy as np
import onnx
import onnx.helper as helper
import onnxruntime as rt
from onnx import numpy_helper as np_helper

model = onnx.load_model("model.onnx")
graph = model.graph


def valueinfo_to_tensor(vi):
    """Creates an all-zeroes numpy tensor from a ValueInfoProto."""

    dims = [x.dim_value for x in vi.type.tensor_type.shape.dim]
    return np.zeros(
        dims, dtype=onnx.mapping.TENSOR_TYPE_TO_NP_TYPE[vi.type.tensor_type.elem_type]
    )


def execute_node(node, context, graph):
    """Call onnxruntime to execute a single node. Input/output provided via context."""

    # onnxruntime unfortunately does not implement run_node as defined by ONNX,
    # it can only execute entire models -- so we create a model which solely
    # consists of our current node.
    node_inputs = list(filter(lambda x: x.name in node.input, graph.input))
    node_inputs += list(filter(lambda x: x.name in node.input, graph.value_info))
    node_outputs = list(filter(lambda x: x.name in node.output, graph.output))
    node_outputs += list(filter(lambda x: x.name in node.output, graph.value_info))
    node_graph = helper.make_graph(
        nodes=[node], name="single-node-exec", inputs=node_inputs, outputs=node_outputs
    )
    node_model = helper.make_model(node_graph)
    input_dict = dict()
    for inp in node.input:
        input_dict[inp] = context[inp]
        print("Input shape for %s: %s" % (inp, context[inp].shape))
    sess = rt.InferenceSession(node_model.SerializeToString())
    output_list = sess.run(None, input_dict)
    for output_ind in range(len(node.output)):
        outp = node.output[output_ind]
        if output_list[output_ind].shape != context[outp].shape:
            raise Exception(
                "Output shapes disagree after node execution: found %s vs expected %s"
                % (str(output_list[output_ind].shape.shape), str(context[outp].shape))
            )
        context[outp] = output_list[output_ind]
        print("Output shape for %s: %s" % (outp, context[outp].shape))


# first, we need to make sure that every variable required by the graph has
# some buffer associated with it. this includes graph inputs (which includes
# the input data as well as the trained parameters) and the graph ValueInfo
# (intermediate tensors between layers)
# we'll keep all our buffers in this dict here:
execution_context = dict()
# make empty tensors for all the graph inputs and outputs
for vi in graph.input:
    new_tensor = valueinfo_to_tensor(vi)
    execution_context[vi.name] = new_tensor
for vi in graph.output:
    new_tensor = valueinfo_to_tensor(vi)
    execution_context[vi.name] = new_tensor
# make empty tensors for all intermediate buffers
# TODO are we guaranteed to have the .value_info filled?
# do we need to call ONNX shape inference first?
for vi in graph.value_info:
    new_tensor = valueinfo_to_tensor(vi)
    execution_context[vi.name] = new_tensor
# fill in the constants provided by the initializers (TensorProto to npy)
for t in graph.initializer:
    execution_context[t.name] = np_helper.to_array(t)

# now call each node in the graph nodes list
# we can simply walk down the list since the ONNX spec guarantees that it is
# topologically sorted
all_used_ops = set()
for node in graph.node:
    print("Node name: %s Type: %s" % (node.name, node.op_type))
    all_used_ops.add(node.op_type)
    print("Input(s): " + str(node.input))
    print("Output(s): " + str(node.output))
    print("Attribute(s): " + str(node.attribute))
    execute_node(node, execution_context, graph)

print("Final output(s): ")
print(execution_context[graph.output[0].name])
