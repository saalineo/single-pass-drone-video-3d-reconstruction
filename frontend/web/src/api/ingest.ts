export interface UploadResponse {
  mission_id: string;
  run_id: string;
  temporal_workflow_id: string;
  status: string;
  message: string;
}

export async function uploadVideo(
  file: File,
  name?: string,
  preset: string = 'standard',
  onProgress?: (pct: number, loaded: number, total: number) => void
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('video', file);
    if (name) formData.append('name', name);
    formData.append('preset', preset);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          onProgress(pct, e.loaded, e.total);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          resolve(res as UploadResponse);
        } catch (err) {
          reject(new Error('Failed to parse server response'));
        }
      } else {
        let errMessage = `Upload failed with status ${xhr.status}`;
        try {
          const res = JSON.parse(xhr.responseText);
          if (res.error) errMessage = res.error;
        } catch (_) {}
        reject(new Error(errMessage));
      }
    };

    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.ontimeout = () => reject(new Error('Upload request timed out'));

    xhr.open('POST', '/v1/ingest/upload');
    xhr.send(formData);
  });
}
