import { describe, expect, it } from "vitest";

import { estFormule, evaluerFormule } from "./formule";

describe("estFormule", () => {
  it("reconnaît un texte commençant par =", () => {
    expect(estFormule("=1+2")).toBe(true);
    expect(estFormule("  =1+2")).toBe(true);
    expect(estFormule("1+2")).toBe(false);
    expect(estFormule("1 200")).toBe(false);
  });
});

describe("evaluerFormule", () => {
  it("additionne et soustrait", () => {
    expect(evaluerFormule("=1200+350,50")).toBe("1 550,50");
    expect(evaluerFormule("=5000-1200")).toBe("3 800");
    expect(evaluerFormule("=100-250")).toBe("-150");
  });

  it("multiplie et divise avant d'additionner", () => {
    expect(evaluerFormule("=1000*3")).toBe("3 000");
    expect(evaluerFormule("=12000/4")).toBe("3 000");
    expect(evaluerFormule("=100+50*2")).toBe("200");
    expect(evaluerFormule("=(1000+500)*2")).toBe("3 000");
    expect(evaluerFormule("=((2+3)*(4-1))/5")).toBe("3");
  });

  it("lit la virgule, le point, les espaces et le signe moins typographique", () => {
    expect(evaluerFormule("= 1 200 000,50 + 0.25")).toBe("1 200 000,75");
    expect(evaluerFormule("=1 200+1 000")).toBe("2 200");
    expect(evaluerFormule("=−500+200")).toBe("-300");
    expect(evaluerFormule("=-(100+50)")).toBe("-150");
  });

  it("calcule exactement et arrondit au centime, moitié vers le haut", () => {
    expect(evaluerFormule("=0,1+0,2")).toBe("0,30");
    expect(evaluerFormule("=10/3")).toBe("3,33");
    expect(evaluerFormule("=0,005*1")).toBe("0,01");
    expect(evaluerFormule("=-0,005*1")).toBe("-0,01");
    expect(evaluerFormule("=0,004")).toBe("0");
  });

  it("refuse une formule fausse ou une division par zéro", () => {
    for (const texte of [
      "=",
      "=12++",
      "=12+",
      "=(1+2",
      "=1+2)",
      "=abc",
      "=1,2,3",
      "=5/0",
      "=5/(2-2)",
    ]) {
      expect(evaluerFormule(texte)).toBeNull();
    }
  });

  it("refuse un texte démesuré sans planter", () => {
    expect(evaluerFormule(`=${"(".repeat(100)}1${")".repeat(100)}`)).toBeNull();
    expect(evaluerFormule(`=${"-".repeat(100_000)}1`)).toBeNull();
  });
});
