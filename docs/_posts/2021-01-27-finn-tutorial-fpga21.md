---
layout: post
title:  "FINN tutorial at FPGA'21"
author: "Yaman Umuroglu"
---

*This event has now concluded. You can find the materials at the bottom of this page.*

We're delighted to announce a two-hour FINN tutorial as part of the [FPGA'21 conference](https://www.isfpga.org).
Details are as follows:

* **Date:** 28 February 2021 (Sunday)
* **Time:**
    * Pacific Standard Time (PST) 10:30 AM – 1:30 PM
    * Central European Time (CET) 19:30 PM – 21:30 PM
* **Format:** Virtual event, Zoom call with hands-on Jupyter notebook lab
    * Zoom and Jupyter links will be sent to confirmed participants via e-mail

## Description

Mixing machine learning into high-throughput, low-latency edge applications needs co-designed solutions to meet the performance requirements. Quantized Neural Networks (QNNs) combined with custom FPGA dataflow implementations offer a good balance of performance and flexibility, but building such implementations by hand is difficult and time-consuming.

In this tutorial, we will introduce FINN, an open-source experimental framework by Xilinx Research Labs to help the broader community explore QNN inference on FPGAs. Providing a full-stack solution from quantization-aware training to bitfile, FINN generates high-performance dataflow-style FPGA architectures customized for each network. Participants will be introduced to efficient inference with QNNs and streaming dataflow architectures, the components of the project’s open-source ecosystem, and gain hands-on experience training a quantized neural network with Brevitas and deploying it with FINN.

## Practical Information

Some prior knowledge of FPGAs, Vivado HLS, PyTorch and neural network training is recommended, but not required.

This will be a virtual event, with a Zoom video call and a hands-on Jupyter notebook lab.
Registered participants will get access to a FINN setup running in the cloud.
There are no special technical requirements besides a browser and Zoom client.

Connect with us and the other participants on the [tutorial Gitter channel](https://gitter.im/xilinx-finn/tutorial-fpga21),
or join the [FINN Gitter channel](https://gitter.im/xilinx-finn/community).

## Agenda

* Part I: Introduction
    * An introduction to FINN, QNNs and streaming dataflow architectures
    * The FINN open-source community
    * Tour of FINN GitHub repositories

* Part II: Hands-on lab: Training and deploying an MLP for network intrusion detection
    * Training a quantized MLP on the UNSW-NB15 dataset with Brevitas
    * Design space exploration and accelerator generation with the FINN compiler

* Demo + Conclusion

## Organization

* Yaman Umuroglu, Michaela Blott, Jon Ander Lezeta and Felix Paul Jentzsch, Xilinx Research Labs
* Zaid Al-Ars and Jakoba Petri-Koenig, TU Delft
* Holger Froening and Hendrik Borras, Heidelberg University

## Materials

* Part I: Introduction
    * [Live recording](https://www.youtube.com/watch?v=zw2aG4PhzmA&amp%3Bindex=2)
    * [Slides](https://github.com/Xilinx/finn/blob/github-pages/docs/finn-isfpga21-tutorial-part1-slides.pdf)

* Part II: Hands-on lab: Training and deploying an MLP for network intrusion detection
   * [Slides](http://bit.ly/finn-tutorial-fpga21-hands-on-slides)
   * [Jupyter notebooks](http://bit.ly/finn-tutorial-fpga21-notebooks)
