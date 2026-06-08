# Adobe Connect Local Recording Stitcher

[![English](https://img.shields.io/badge/Language-English-blue)](README.md)
[![فارسی](https://img.shields.io/badge/Language-فارسی-green)](README.fa.md)

This guide will walk you through downloading an Adobe Connect recording from your university's server and converting it into a standard MP4 video file using a local Python script and FFmpeg.

### Acknowledgments and Inspiration
This project is heavily inspired by the [Vadana Class Downloader (VCD)](https://github.com/IAUCourseExp/VCD/blob/main/VCD.py). While VCD automates the live downloading and rendering of Azad University's Adobe Connect videos over the network, this tool is designed for **offline processing**. It specifically targets FUM's modified Adobe Connect system (Webinar) by relying on a native ZIP download trick to bypass network timeouts, parsing the XML data locally, and stitching the multi-segment timeline together with FFmpeg.

---

## Step 1: Download the ZIP File

1. Locate your Adobe Connect **Recording ID**. For instance after logging in, on the class records page at [https://pooya.um.ac.ir/educ/educfac/VClassRecords.php](https://pooya.um.ac.ir/educ/educfac/VClassRecords.php) click on a session. The URL will look like this: https://webinar3.um.ac.ir/[RECORDING_ID]/.
2. By default, the server names the ZIP file after the recording ID, but you can rename it directly in the download link by replacing the second `[RECORDING_ID]` with your desired name.
3. Use the following URL structure:

```text
https://webinar3.um.ac.ir/[RECORDING_ID]/output/[DESIRED_NAME].zip?download=zip
```

> **Example:** If your ID is `p1v8fvjnzey5` and you want the file to be named `Session3`, your download link will be:
> [https://webinar3.um.ac.ir/p1v8fvjnzey5/output/Session3.zip?download=zip](https://webinar3.um.ac.ir/p1v8fvjnzey5/output/Session3.zip?download=zip)

---

## Step 2: Extract the Archives

Once the download is complete, extract the contents of the ZIP file into a new folder on your computer. 

*Note: The script will automatically name the final MP4 video after this extracted folder (e.g., if the folder is named `Session3`, the output will be `Session3.mp4`).*

---

## Step 3: Prerequisites

Before running the script, ensure you have the following installed on your system:
* **Python 3.x** installed and added to your PATH.
* **FFmpeg** installed and added to your system's PATH.
* *(Optional)* A dedicated NVIDIA GPU. The script attempts to use CUDA (`h264_nvenc`) by default for incredibly fast encoding. If you don't have one, you can disable it in the script settings.

---

## Step 4: Run the Conversion Script

1. Create a new text file inside the extracted folder (where the `.flv` and `.xml` files are located).
2. Rename the file to `stitch.py` (ensure the file extension changes from `.txt` to `.py`).
3. Open `stitch.py` in a text editor, paste the Python script at [https://github.com/S0HElL/webinar-offline/blob/main/stitch.py](https://github.com/S0HElL/webinar-offline/blob/main/stitch.py), and save it.
4. Open a Terminal / Command Prompt inside the folder where `stitch.py` is located.
5. Run the script using Python:
   ```bash
   python stitch.py
   ```
6. Once the process completes, you will find your correctly-timed, combined video named after the folder (e.g., `Session3.mp4`) in the same directory.
