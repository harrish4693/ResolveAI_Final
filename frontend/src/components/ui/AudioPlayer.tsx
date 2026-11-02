import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Volume2, AlertCircle } from "lucide-react";

interface AudioPlayerProps {
  url: string;
  className?: string;
}

export const AudioPlayer: React.FC<AudioPlayerProps> = ({ url, className = "" }) => {
  const [audioSrc, setAudioSrc] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let isMounted = true;

    const fetchAudio = async () => {
      try {
        const endpoint = url.startsWith("/api/") ? url.substring(4) : url;
        const response = await api.get(endpoint, {
          responseType: "blob",
        });

        if (isMounted) {
          objectUrl = URL.createObjectURL(response.data);
          setAudioSrc(objectUrl);
        }
      } catch (err) {
        console.error("Failed to fetch audio", err);
        if (isMounted) setError(true);
      }
    };

    fetchAudio();

    return () => {
      isMounted = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [url]);

  if (error) {
    return (
      <div className={`flex items-center gap-1.5 text-xs text-destructive ${className}`}>
        <AlertCircle className="size-3.5" />
        Audio recording unavailable
      </div>
    );
  }

  if (!audioSrc) {
    return (
      <div className={`flex items-center gap-2 text-xs text-muted-foreground animate-pulse ${className}`}>
        <Volume2 className="size-3.5 animate-spin" />
        Loading voice message…
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 bg-background/50 p-1.5 rounded-lg border ${className}`}>
      <Volume2 className="size-4 text-primary shrink-0 ml-1" />
      <audio src={audioSrc} controls className="h-8 max-w-[240px] w-full" />
    </div>
  );
};
