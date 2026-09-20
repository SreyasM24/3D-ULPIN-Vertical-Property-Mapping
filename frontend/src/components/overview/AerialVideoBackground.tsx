import React, { useState, useEffect } from 'react';

/**
 * 3-Image Slideshow Background using ONLY the uploaded assets:
 * - delhi.jpg
 * - Mumbai.png
 * - hyderabad.jpg
 * 
 * Features:
 * - 4.5s display time per slide
 * - Smooth 1-second crossfade transition between images
 * - Continuous loop (Delhi -> Mumbai -> Hyderabad -> Delhi...)
 * - Full-bleed background with object-cover and subtle 9% crop (scale 1.09)
 * - Subtle dark overlay ensuring hero text remains crisp and highly legible
 * - Zero video elements, zero debug labels or synthetic badges
 */
const SLIDES = [
  { src: '/delhi.jpg', alt: 'Delhi Cadastral Survey' },
  { src: '/Mumbai.png', alt: 'Mumbai Urban Survey' },
  { src: '/hyderabad.jpg', alt: 'Hyderabad Geo Survey' },
];

const DISPLAY_DURATION_MS = 4500; // 4.5 seconds per image

export const AerialVideoBackground: React.FC = () => {
  const [currentIndex, setCurrentIndex] = useState<number>(0);

  // Preload all 3 images for seamless zero-flicker crossfading
  useEffect(() => {
    SLIDES.forEach((slide) => {
      const img = new Image();
      img.src = slide.src;
    });
  }, []);

  // Interval timer for 4-5 second slide cycle with automatic looping
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % SLIDES.length);
    }, DISPLAY_DURATION_MS);

    return () => clearInterval(timer);
  }, []);

  return (
    <div
      className="absolute inset-0 w-full h-full pointer-events-none overflow-hidden select-none"
      aria-hidden="true"
    >
      {/* 
        Full-bleed stacked images with object-cover, 9% crop (scale 1.09),
        and smooth 1000ms crossfade transitions in natural normal colors
      */}
      {SLIDES.map((slide, idx) => {
        const isActive = idx === currentIndex;
        return (
          <img
            key={slide.src}
            src={slide.src}
            alt={slide.alt}
            className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-1000 ease-in-out ${
              isActive ? 'opacity-100 z-10' : 'opacity-0 z-0 pointer-events-none'
            }`}
            style={{
              transform: 'scale(1.09) translate3d(0, 0, 0)',
              transformOrigin: 'center center',
            }}
          />
        );
      })}

      {/* Subtle black overlay (18% opacity) over the images to slightly dim photos for readability */}
      <div className="absolute inset-0 z-20 bg-black/[0.18] pointer-events-none" />
    </div>
  );
};
