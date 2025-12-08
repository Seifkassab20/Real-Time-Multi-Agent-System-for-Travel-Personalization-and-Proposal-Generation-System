import torch
from ASR.new_src.preprocess_audio import audio_utils
from ASR.new_src.load_model import LoadSeamlessModel
from dotenv import load_dotenv
import os
load_dotenv()
utils=audio_utils()
ASR=LoadSeamlessModel()
processor,model= ASR._load()


def transcribe(  audio_path: str, tgt_lang: str = "arb"):
    print(f"\n[inference] Starting CHUNKED transcription (lang={tgt_lang})...")
    chunk_results = []
    waveform = utils.preprocess_audio(audio_path)
    sr = 16000
    duration_sec = len(waveform) / sr

    # ---- Chunk audio into 20s windows ----
    print("[audio] Chunking audio into 20-second segments...")
    chunks = utils.chunk_audio(torch.tensor(waveform), sr=sr)
    print(f"[audio] Total chunks: {len(chunks)}")

    final_text = ""
    device = torch.device(ASR.device)  # ensure correct type
    for i, chunk in enumerate(chunks, start=1):
        print(f"[chunk {i}/{len(chunks)}] Processing...")

        # Convert audio chunk to model inputs
        inputs = processor(
            audio=chunk.astype(float),
            sampling_rate=sr,
            return_tensors="pt"
        ).to(device)

        with torch.no_grad():
            output = model.generate(
                **inputs,
                tgt_lang=tgt_lang,
                max_new_tokens=256,
                return_dict_in_generate=True,
                output_scores=True
            )

        # -----------------------------
        # 1. Extract decoded token ids
        # -----------------------------
        token_ids = output.sequences[0]
        token_ids = torch.tensor(token_ids, dtype=torch.long).unsqueeze(0)

        # -----------------------------
        # 2. Decode text
        # -----------------------------
        text = processor.batch_decode( token_ids, skip_special_tokens=True )[0]

        # -----------------------------
        # 3. Compute per-token confidence
        # -----------------------------
        scores = output.scores         
        logits = torch.stack(scores)    

        probs = torch.softmax(logits, dim=-1)         
        log_probs = torch.log_softmax(logits, dim=-1) 

        entropy = -(probs * log_probs).sum(dim=-1)       # (T,)
        entropy = entropy.cpu()

        # Normalize entropy into confidence (0 to 1)
        max_entropy = torch.log(torch.tensor(logits.size(-1)))
        confidence = 1.0 - (entropy / max_entropy)

        confidence = confidence.tolist()  # list of floats

        # confidence = list of lists → flatten to a single list of floats
        flat_confidence = [c for sublist in confidence for c in (sublist if isinstance(sublist, list) else [sublist])]

        # Now compute average safely
        avg_conf = sum(flat_confidence) / len(flat_confidence)

        print(f"[chunk {i}] Text: {text}")
        print(f"[chunk {i}] Avg confidence: {avg_conf:.3f}")
        chunk_results.append({
            "text": text,
            "token_confidence": flat_confidence,
            "avg_confidence": avg_conf,
        })

        final_text += " " + text

        if device.type == "mps":
            torch.mps.empty_cache()
    return final_text.strip(), chunk_results  
            
