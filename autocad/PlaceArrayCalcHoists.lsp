;;; ==========================================================================
;;;  PlaceArrayCalcHoists.lsp  -  ArrayCalc pick points -> AutoCAD hoist blocks
;;;  AutoCAD 2025 (LISPSYS = 1). Save/keep this file as UTF-8 (Cyrillic name).
;;;
;;;  Command:  ACHOISTS
;;;    1. pick the CSV written by extract_arraycalc_hoists.py (metres)
;;;    2. dialog: tick sources that are single-point hangs, label layout
;;;       (left/right or top/bottom) + per-source override, solid colour,
;;;       department text, weight suffix, symbol scale
;;;    3. one block insert per pick at (x, y, z) - z = hoist height;
;;;       optional rotation of the whole layout about 0,0 (Z unchanged)
;;;
;;;
;;;  AutoCAD for Mac (no ActiveX there): the same file loads, ACHOISTS opens
;;;  the same dialog and places the hoists with plain AutoLISP (entmake /
;;;  entmod). Same results. If the dialog cannot be loaded there, ACHOISTS
;;;  falls back to command-line prompts by itself.
;;;  ACHOISTS_CLI = the command-line version on any platform.
;;;  Testing the Mac path on Windows: (setq *ach:simulate-mac* T), then
;;;  ACHOISTS / ACHOISTS_CLI behave as on a Mac (plain-AutoLISP engine, Mac
;;;  dialog layout, no font repair). (setq *ach:force-engine* "lisp") swaps
;;;  only the engine.
;;;
;;;  Non-interactive core (for scripts / testing, never opens a dialog):
;;;    (achoists-run CSVPATH SINGLES COLOR DEPT SUFFIX DELETEOLD)
;;;      layout = *ach:label-layout* (default "side")
;;;    (achoists-run-layout CSVPATH SINGLES COLOR DEPT SUFFIX DELETEOLD LAYOUT)
;;;      LAYOUT   "side" (left/right, auto-mirror) or "topbottom"
;;;    (achoists-run-ex CSVPATH SINGLES COLOR DEPT SUFFIX DELETEOLD OPTS)
;;;      SINGLES  list of source names placed on their single pick, e.g. '("RING 1")
;;;      COLOR    ACI integer (1 = red) or acad_truecolordlg list, e.g. '((62 . 1) (420 . 16711680))
;;;      OPTS     assoc list, any of:
;;;               ("factor" . drawing-units-per-metre)  default from INSUNITS
;;;               ("scale" . symbol-scale)              default *ach:symbol-scale*
;;;               ("layout" . "side" | "topbottom")      default *ach:label-layout*
;;;               ("sides" . (("MAIN LR" . "auto") ("SUBS LR2" . "topbottom") ...))
;;;                 per source: "default" (= layout; same as missing),
;;;                 "auto" (left/right, mirror close pairs), "right", "left",
;;;                 "topbottom" (PT-NAME above the symbol, LOAD below)
;;;               ("blockfile" . "C:/path/HoistPoint.dwg")
;;;               ("rotation" . degrees)   rotate X/Y about 0,0, CCW +, default 0
;;;               ("rotate-symbols" . T)   also rotate the symbols (labels
;;;                                        always stay upright on the page)
;;;               ("engine" . "lisp")      plain-AutoLISP (Mac) engine;
;;;                                        default: ActiveX when available
;;;    Returns (T . summary-text) or (nil . error-text).
;;; ==========================================================================

;;; ------------------------------ platform ---------------------------------
;; Load order matters on AutoCAD for Mac: if any form fails while the file is
;; loading, everything after it is never defined. So this section uses only
;; functions that exist on both platforms, and the two commands are defined
;; right here, before anything else. The file is plain ASCII on purpose (no
;; encoding questions on either platform).
(setq *ach:loaded* nil *ach:stage* "start")

;; T on AutoCAD for Mac (PLATFORM reads e.g. "Mac OS X Version 10.16 (x86_64)";
;; on Windows "Microsoft Windows NT Version 10.0 (x64)").
;; *ach:simulate-mac* = T makes Windows behave as a Mac (testing only).
(defun ach:mac-p ()
  (or *ach:simulate-mac*
      (wcmatch (strcase (vl-princ-to-string (getvar "PLATFORM"))) "*MAC*,*DARWIN*")))

;; Shown by the commands when the file did not finish loading.
(defun ach:load-failed ()
  (princ (strcat "\nACHOISTS: PlaceArrayCalcHoists.lsp did not finish loading"
                 " (it stopped in: " (vl-princ-to-string *ach:stage*) ")."
                 "\nLoad it again with APPLOAD and send the '; error:' line"
                 " shown on the command line."))
  (princ))

;; The dialog on Windows; on AutoCAD for Mac *ach:mac-ui* ("dialog" by default,
;; falling back to the prompts if the dialog cannot be loaded).
(defun c:ACHOISTS ()
  (if (and *ach:loaded* ach:command)
    (ach:command (if (or (ach:mac-p) (not (ach:activex-p))) *ach:mac-ui* "dialog"))
    (ach:load-failed)))

;; Command-line prompts on any platform.
(defun c:ACHOISTS_CLI ()
  (if (and *ach:loaded* ach:command)
    (ach:command "prompts")
    (ach:load-failed)))

;; ActiveX (vl-load-com, vla-*, vlax-*) is Windows-only. It is loaded the first
;; time it is needed, never at load time and never on a Mac.
(defun ach:activex-p ()
  (and (not (ach:mac-p))
       (progn
         (if (not *ach:ax-checked*)
           (setq *ach:ax-checked* T
                 *ach:ax-ok* (and (not (vl-catch-all-error-p
                                         (vl-catch-all-apply 'vl-load-com nil)))
                                  (if vlax-get-acad-object T))))
         *ach:ax-ok*)))

;; String from Unicode code points, so the file itself stays ASCII. Returns
;; FALLBACK if this AutoLISP cannot make those characters (LISPSYS 0).
(defun ach:ustr (codes fallback / s)
  (setq s (vl-catch-all-apply
            '(lambda () (apply 'strcat (mapcar 'chr codes)))
            nil))
  (if (and (= (type s) 'STR)
           (= (strlen s) (length codes))
           (= (ascii s) (car codes)))
    s
    fallback))

(setq *ach:stage* "settings")
;;; ---------------------------- USER SETTINGS -------------------------------
;; Block name used in the drawing. The block DWG next to this file is
;; inserted and renamed to this name when the drawing does not have it yet.
;; "tochka" in Cyrillic (U+0442 U+043E U+0447 U+043A U+0430).
(setq *ach:block-name*    (ach:ustr '(1090 1086 1095 1082 1072) "tochka"))
;; Other names accepted as "the hoist block" if already present in a drawing
;; (symbol-table lookups are case-insensitive anyway).
;; Cyrillic "Tochka" and "TOCHKA".
(setq *ach:block-aliases*
  (vl-remove nil
    (list (ach:ustr '(1058 1086 1095 1082 1072) nil)
          (ach:ustr '(1058 1054 1063 1050 1040) nil)
          "x-2D_RIG_POINTS$0$RIG_ONE_TON")))
;; Block DWG file shipped next to this .lsp (geometry drawn in millimetres).
(setq *ach:block-file*    "HoistPoint.dwg")
;; Units assumed for a block definition whose Units property is "Unitless".
;; 4 = millimetres (HoistPoint.dwg is drawn in mm).
(setq *ach:block-default-units* 4)
;; Layer for the inserts (created if missing) and its colour for new layers.
(setq *ach:layer*         "AC_HOISTS")
(setq *ach:layer-color*   7)
;; Attribute tags inside the block.
(setq *ach:tag-dept*      "PT-NAME")   ; department text, e.g. "Sound" (or Cyrillic "Zvuk")
(setq *ach:tag-load*      "LOAD")      ; weight, e.g. "664 kg"
;; Defaults shown in the dialog (last used values are remembered).
(setq *ach:default-dept*   "Sound")
(setq *ach:default-suffix* " kg")
(setq *ach:default-color*  '((62 . 1)))   ; red
(setq *ach:symbol-scale*   1.0)           ; 1.0 = symbol at its drawn mm size
;; Force solid fills (HATCH / SOLID) in the block definition to ByBlock so the
;; insert colour drives them. Outline, crosshair and texts stay ByLayer.
(setq *ach:fill-byblock*   T)
;; "auto" label side: front/rear picks closer than this (metres, times the
;; symbol scale) in plan Y get the lower-X pick's labels mirrored to the left
;; (0.75 m = crosshair half-length + label height of the 1:1 symbol).
(setq *ach:flip-clearance-m* 0.75)
;; Label layout used for every source left on "as layout":
;;   "side"      = labels right of the symbol, lower-X hoist of a close
;;                 front/rear pair mirrored to the left (original behaviour)
;;   "topbottom" = department text centred above, weight centred below
(setq *ach:label-layout*  "side")
;; Top/bottom: clear gap between the symbol (circle + crosshair) and the
;; text, as a fraction of the symbol's half-height (0.15 -> ~62 mm at 1:1).
(setq *ach:tb-gap-ratio*  0.15)
;; Top/bottom as the LAYOUT (not forced per source): a front/rear pair that
;; sits closer than this on the page (metres, times the symbol scale) - less
;; than one label width apart in X and less than two label stacks in Y -
;; would collide, so that pair keeps "auto" left/right labels instead.
;; Set *ach:tb-fallback* to nil to always use top/bottom.
(setq *ach:tb-fallback*   T)
(setq *ach:tb-clear-x-m*  0.85)
(setq *ach:tb-clear-y-m*  1.5)
;; TrueType face used to repair the attribute text style if its font is
;; missing (the block's own style x-2D_RIG_POINTS$0$RIG_POINTS = Arial Narrow).
(setq *ach:text-font*     "Arial Narrow")
;; Registered application name for the xdata that marks our inserts.
(setq *ach:xdata-app*     "ACHOISTS")
;; How ACHOISTS asks for its options on AutoCAD for Mac: "dialog" (the same
;; DCL dialog as on Windows - DCL exists on Mac since AutoCAD 2021; falls
;; back to the prompts if it cannot be loaded) or "prompts" (command line).
(setq *ach:mac-ui*        "dialog")
;; Placement engine: nil = automatic (ActiveX on Windows, plain AutoLISP
;; where ActiveX is missing). Set to "lisp" to run the Mac engine on Windows.
(setq *ach:force-engine*  nil)
;; Testing only: T makes Windows behave as AutoCAD for Mac (see header).
(if (not (boundp '*ach:simulate-mac*)) (setq *ach:simulate-mac* nil))
;; Colour names accepted by the command-line prompt (ACI numbers 1-255 too).
(setq *ach:color-names*
  '(("red" . 1) ("yellow" . 2) ("green" . 3) ("cyan" . 4) ("blue" . 5)
    ("magenta" . 6) ("white" . 7) ("grey" . 8) ("gray" . 8)
    ("lightgrey" . 9) ("lightgray" . 9) ("orange" . 30)))
;;; -------------------------------------------------------------------------


;;; ============================== helpers ==================================
(setq *ach:stage* "helpers")

(defun ach:lower (s) (if s (strcase s T) ""))

(defun ach:trim (s) (if s (vl-string-trim " \t\r\n" s) ""))

;; Keep only [a-z0-9_] - strips a UTF-8 BOM (U+FEFF, or its ANSI mojibake)
;; and stray spaces/quotes from header names.
(defun ach:clean-key (s / out c)
  (setq out '())
  (foreach c (vl-string->list (ach:lower s))
    (if (or (and (>= c 48) (<= c 57)) (and (>= c 97) (<= c 122)) (= c 95))
      (setq out (cons c out))))
  (vl-list->string (reverse out)))

;; Split one CSV line; handles "quoted, fields" and "" escapes.
(defun ach:split-csv (line / chars c field fields inq)
  (setq chars (vl-string->list line) field '() fields '() inq nil)
  (while chars
    (setq c (car chars) chars (cdr chars))
    (cond
      ((and inq (= c 34) (= (car chars) 34))
       (setq field (cons 34 field) chars (cdr chars)))
      ((= c 34) (setq inq (not inq)))
      ((and (= c 44) (not inq))
       (setq fields (cons (vl-list->string (reverse field)) fields) field '()))
      ((or (= c 13) (= c 10)) nil)
      (T (setq field (cons c field)))))
  (reverse (cons (vl-list->string (reverse field)) fields)))

(defun ach:open-utf8 (path / f)
  ;; LISPSYS 1/2 accept an encoding argument; LISPSYS 0 does not.
  (setq f (vl-catch-all-apply 'open (list path "r" "utf8")))
  (if (vl-catch-all-error-p f) (setq f (open path "r")))
  f)

;; Returns list of rows; each row is an assoc list (("source" . "MAIN LR") ...)
(defun ach:read-csv (path / f line keys vals row rows)
  (if (not (setq f (ach:open-utf8 path)))
    nil
    (progn
      (while (and (not keys) (setq line (read-line f)))
        (if (/= (ach:trim line) "")
          (setq keys (mapcar 'ach:clean-key (ach:split-csv line)))))
      (while (setq line (read-line f))
        (if (/= (ach:trim line) "")
          (progn
            (setq vals (ach:split-csv line) row '())
            (mapcar '(lambda (k v) (setq row (cons (cons k (ach:trim v)) row)))
                    keys vals)
            (setq rows (cons (reverse row) rows)))))
      (close f)
      (list keys (reverse rows)))))

(defun ach:get (row key / p) (if (setq p (assoc key row)) (cdr p) ""))

(defun ach:num (row key) (atof (ach:get row key)))

(defun ach:truthy (s)
  (if (member (strcase (ach:trim s)) '("1" "TRUE" "YES" "Y" "T")) T nil))

(defun ach:kind (row) (ach:lower (ach:get row "pick_kind")))

;; -> (names meta)   meta item: (name single-available has-single-row system)
(defun ach:sources (rows / names meta src e)
  (foreach r rows
    (setq src (ach:get r "source"))
    (if (not (assoc src meta))
      (setq names (cons src names)
            meta  (cons (list src nil nil (ach:get r "system")) meta)))
    (setq e (assoc src meta))
    (if (ach:truthy (ach:get r "single_available"))
      (setq meta (subst (list src T (nth 2 e) (nth 3 e)) e meta)
            e    (assoc src meta)))
    (if (= (ach:kind r) "single")
      (setq meta (subst (list src (nth 1 e) T (nth 3 e)) e meta))))
  (list (reverse names) meta))

(defun ach:can-single (meta src / e)
  (setq e (assoc src meta))
  (and e (nth 1 e) (nth 2 e)))

;; Default: front + rear. Sources in SINGLES: their single row only.
(defun ach:filter-rows (rows singles / k out)
  (foreach r rows
    (setq k (ach:kind r))
    (if (member (ach:get r "source") singles)
      (if (= k "single") (setq out (cons r out)))
      (if (member k '("front" "rear")) (setq out (cons r out)))))
  (reverse out))

;; Metres per drawing unit for an INSUNITS / block Units code.
(defun ach:metres-per-unit (u)
  (cdr (assoc u '((1 . 0.0254) (2 . 0.3048) (3 . 1609.344) (4 . 0.001)
                  (5 . 0.01) (6 . 1.0) (7 . 1000.0) (8 . 2.54e-08)
                  (9 . 2.54e-05) (10 . 0.9144) (11 . 1.0e-10) (12 . 1.0e-09)
                  (13 . 1.0e-06) (14 . 0.1) (15 . 10.0) (16 . 100.0)
                  (17 . 1.0e9) (18 . 1.495978707e11) (19 . 9.4607304725808e15)
                  (20 . 3.0856775814914e16) (21 . 0.30480060960122)))))

(defun ach:unit-name (u)
  (cond ((cdr (assoc u '((0 . "unitless") (1 . "inches") (2 . "feet") (3 . "miles")
                         (4 . "mm") (5 . "cm") (6 . "m") (7 . "km") (10 . "yards")
                         (14 . "dm") (21 . "US survey feet")))))
        (T (strcat "INSUNITS " (itoa u)))))

;; Drawing units per metre from INSUNITS, or nil when unitless/unknown.
(defun ach:factor-from-insunits (/ m)
  (if (setq m (ach:metres-per-unit (getvar "INSUNITS"))) (/ 1.0 m)))

(defun ach:fmt-load (w suffix)
  (if (> w 0.0)
    (strcat (itoa (fix (+ w 0.5))) suffix)
    (strcat "?" suffix)))

(defun ach:color-spec (c)
  ;; Normalise to an acad_truecolordlg style list.
  (cond ((numberp c) (list (cons 62 (fix c))))
        ((and (listp c) (assoc 62 c)) c)
        (T *ach:default-color*)))

(defun ach:color-text (c / tc)
  (setq c (ach:color-spec c))
  (cond ((assoc 430 c) (cdr (assoc 430 c)))
        ((setq tc (cdr (assoc 420 c)))
         (strcat "RGB " (itoa (lsh tc -16)) "," (itoa (logand (lsh tc -8) 255))
                 "," (itoa (logand tc 255))))
        (T (strcat "ACI " (itoa (cdr (assoc 62 c)))))))

(defun ach:join (lst sep / s)
  (setq s "")
  (foreach x lst (setq s (if (= s "") x (strcat s sep x))))
  s)

;;; ============================ block handling =============================
(setq *ach:stage* "block handling")

(defun ach:block-exists-p (name)
  (and name (tblsearch "BLOCK" name)))

;; Name of the hoist block present in the drawing, or nil.
(defun ach:find-block (doc / found names unames)
  (setq names (cons *ach:block-name* *ach:block-aliases*))
  (foreach n names
    (if (and (not found) (ach:block-exists-p n)) (setq found n)))
  (if (not found)
    (progn
      (setq unames (mapcar 'strcase names))
      (vlax-for b (vla-get-Blocks doc)
        (if (and (not found)
                 (= (vla-get-IsLayout b) :vlax-false)
                 (= (vla-get-IsXRef b) :vlax-false)
                 (member (strcase (vla-get-Name b)) unames))
          (setq found (vla-get-Name b))))))
  ;; return the drawing's own spelling of the name
  (if found (vla-get-Name (vla-Item (vla-get-Blocks doc) found))))

;; Look for HoistPoint.dwg in the usual places.
(defun ach:find-block-file (csvpath / cands lsp d p hit sep)
  (setq sep (if (ach:mac-p) "/" "\\"))
  (setq cands (list (getenv "ACHOISTS_BlockFile") (findfile *ach:block-file*)))
  (if (setq lsp (findfile "PlaceArrayCalcHoists.lsp"))
    (setq cands (cons (strcat (vl-filename-directory lsp) sep *ach:block-file*) cands)))
  (setq d (getvar "DWGPREFIX"))
  (setq cands (append cands (list (strcat d *ach:block-file*)
                                  (strcat d "acad-scripts" sep *ach:block-file*))))
  (if csvpath
    (progn
      (setq d (strcat (vl-filename-directory csvpath) sep))
      (setq cands (append cands (list (strcat d *ach:block-file*)
                                      (strcat d "acad-scripts" sep *ach:block-file*))))))
  (foreach p cands
    (if (and (not hit) p (/= p "") (findfile p)) (setq hit (findfile p))))
  hit)

;; Insert the block DWG as a definition (no visible insert), rename it to
;; *ach:block-name*. Returns the block name or nil.
(defun ach:load-block-file (doc ms path / ref bname blk)
  (setq path (vl-string-translate "/" "\\" path))
  (setq ref (vl-catch-all-apply 'vla-InsertBlock
              (list ms (vlax-3d-point 0.0 0.0 0.0) path 1.0 1.0 1.0 0.0)))
  (if (vl-catch-all-error-p ref)
    (progn (princ (strcat "\nACHOISTS: cannot insert " path ": "
                          (vl-catch-all-error-message ref)))
           nil)
    (progn
      (setq bname (vla-get-Name ref))
      (vla-Delete ref)
      (setq blk (vla-Item (vla-get-Blocks doc) bname))
      (if (and (/= (strcase bname) (strcase *ach:block-name*))
               (not (ach:block-exists-p *ach:block-name*)))
        (progn (vla-put-Name blk *ach:block-name*)
               (setq bname *ach:block-name*)))
      (if (= (vla-get-Units blk) 0)
        (vla-put-Units blk *ach:block-default-units*))
      (setenv "ACHOISTS_BlockFile" path)
      bname)))

;; Put HATCH / SOLID entities of the definition on colour ByBlock.
;; Returns number of fill entities found.
(defun ach:fills-byblock (blk / n)
  (setq n 0)
  (vlax-for e blk
    (if (member (vla-get-ObjectName e) '("AcDbHatch" "AcDbSolid" "AcDbTrace"))
      (progn
        (setq n (1+ n))
        (if (/= (vla-get-Color e) acByBlock)
          (vl-catch-all-apply 'vla-put-Color (list e acByBlock))))))
  n)

;; Tags of the attribute definitions in the block, in order.
(defun ach:block-tags (blk / tags)
  (vlax-for e blk
    (if (= (vla-get-ObjectName e) "AcDbAttributeDefinition")
      (setq tags (cons (vla-get-TagString e) tags))))
  (reverse tags))

;;; ============================== layer ====================================

;; Make sure our layer exists, is on, thawed and unlocked.
(defun ach:ensure-layer (doc name / lays lay)
  (setq lays (vla-get-Layers doc))
  (setq lay (vl-catch-all-apply 'vla-Item (list lays name)))
  (if (vl-catch-all-error-p lay)
    (progn (setq lay (vla-Add lays name))
           (vla-put-Color lay *ach:layer-color*)))
  (vl-catch-all-apply 'vla-put-Lock (list lay :vlax-false))
  (vl-catch-all-apply 'vla-put-LayerOn (list lay :vlax-true))
  (if (/= (strcase (getvar "CLAYER")) (strcase name))
    (vl-catch-all-apply 'vla-put-Freeze (list lay :vlax-false)))
  lay)

;;; ========================== previous inserts =============================

;; Enames of inserts made by earlier runs: our xdata, or (fallback) any
;; insert of the hoist block on our layer.
(defun ach:previous-inserts (bname / ss i e out bn)
  (if (setq ss (ssget "_X" (list (cons 0 "INSERT") (list -3 (list *ach:xdata-app*)))))
    (progn (setq i 0)
           (repeat (sslength ss) (setq out (cons (ssname ss i) out) i (1+ i)))))
  (if (and bname (setq ss (ssget "_X" (list (cons 0 "INSERT") (cons 8 *ach:layer*)))))
    (progn
      (setq i 0)
      (repeat (sslength ss)
        (setq e (ssname ss i) i (1+ i))
        (setq bn (vl-catch-all-apply 'vla-get-EffectiveName (list (vlax-ename->vla-object e))))
        (if (and (not (vl-catch-all-error-p bn))
                 (= (strcase bn) (strcase bname))
                 (not (member e out)))
          (setq out (cons e out))))))
  out)

;;; ======================= attribute helpers ===============================

(defun ach:set-att (ref tag val / hit)
  (foreach a (vlax-invoke ref 'GetAttributes)
    (if (= (strcase (vla-get-TagString a)) (strcase tag))
      (progn (vla-put-TextString a val) (setq hit T))))
  hit)

;; Mirror the attribute positions of one insert to the other side of the
;; insertion point (labels left instead of right). Text stays upright.
(defun ach:flip-atts (ref / ip al nal pt use-ins)
  (setq ip (vlax-get ref 'InsertionPoint))
  (foreach a (vlax-invoke ref 'GetAttributes)
    (setq al  (vla-get-Alignment a)
          nal (cdr (assoc al (list (cons acAlignmentLeft acAlignmentRight)
                                   (cons acAlignmentRight acAlignmentLeft)
                                   (cons acAlignmentTopLeft acAlignmentTopRight)
                                   (cons acAlignmentTopRight acAlignmentTopLeft)
                                   (cons acAlignmentMiddleLeft acAlignmentMiddleRight)
                                   (cons acAlignmentMiddleRight acAlignmentMiddleLeft)
                                   (cons acAlignmentBottomLeft acAlignmentBottomRight)
                                   (cons acAlignmentBottomRight acAlignmentBottomLeft)
                                   (cons acAlignmentCenter acAlignmentCenter)
                                   (cons acAlignmentMiddle acAlignmentMiddle)
                                   (cons acAlignmentTopCenter acAlignmentTopCenter)
                                   (cons acAlignmentMiddleCenter acAlignmentMiddleCenter)
                                   (cons acAlignmentBottomCenter acAlignmentBottomCenter)))))
    (if nal
      (progn
        ;; anchor point: InsertionPoint for Left, TextAlignmentPoint otherwise
        (setq pt (if (= al acAlignmentLeft)
                   (vlax-get a 'InsertionPoint)
                   (vlax-get a 'TextAlignmentPoint)))
        (setq pt (list (- (* 2.0 (car ip)) (car pt)) (cadr pt) (caddr pt)))
        (vla-put-Alignment a nal)
        (if (= nal acAlignmentLeft)
          (vlax-put a 'InsertionPoint pt)
          (vlax-put a 'TextAlignmentPoint pt))))))

;; Extents of the block's own geometry (everything except attribute
;; definitions) in block units, relative to the block base point:
;; ((xmin ymin) (xmax ymax)) or nil.
(defun ach:block-extents (blk / org mn mx r lo hi a b)
  (setq org (vlax-get blk 'Origin))
  (vlax-for e blk
    (if (/= (vla-get-ObjectName e) "AcDbAttributeDefinition")
      (progn
        (setq r (vl-catch-all-apply 'vla-GetBoundingBox (list e 'mn 'mx)))
        (if (not (vl-catch-all-error-p r))
          (progn
            (setq a (vlax-safearray->list mn) b (vlax-safearray->list mx))
            (setq lo (if lo (list (min (car lo) (car a)) (min (cadr lo) (cadr a)))
                            (list (car a) (cadr a)))
                  hi (if hi (list (max (car hi) (car b)) (max (cadr hi) (cadr b)))
                            (list (car b) (cadr b)))))))))
  (if (and lo hi)
    (list (list (- (car lo) (car org)) (- (cadr lo) (cadr org)))
          (list (- (car hi) (car org)) (- (cadr hi) (cadr org))))))

;; Block-local point (block units, from the base point) -> page point:
;; insert position + X/Y scale, rotated by ROT (radians; 0 = page upright).
(defun ach:local->world (ref lp rot / ip sx sy x y)
  (setq ip  (vlax-get ref 'InsertionPoint)
        sx  (vla-get-XScaleFactor ref)
        sy  (vla-get-YScaleFactor ref)
        x   (* (car lp) sx)
        y   (* (cadr lp) sy))
  (list (+ (car ip) (- (* x (cos rot)) (* y (sin rot))))
        (+ (cadr ip) (+ (* x (sin rot)) (* y (cos rot))))
        (caddr ip)))

;; Attribute definitions: ((TAG alignment local-point rotation style) ...), the
;; point being the alignment anchor (insertion point for Left-aligned text),
;; relative to the block base point, in block units.
(defun ach:block-attdefs (blk / org al pt out)
  (setq org (vlax-get blk 'Origin))
  (vlax-for e blk
    (if (= (vla-get-ObjectName e) "AcDbAttributeDefinition")
      (progn
        (setq al (vla-get-Alignment e)
              pt (if (= al acAlignmentLeft)
                   (vlax-get e 'InsertionPoint)
                   (vlax-get e 'TextAlignmentPoint)))
        (setq out (cons (list (strcase (vla-get-TagString e)) al
                              (list (- (car pt) (car org)) (- (cadr pt) (cadr org)))
                              (vla-get-Rotation e)
                              (vla-get-StyleName e))
                        out)))))
  out)

;; Attribute references always use their definition's text style (repairs
;; inserts whose attributes were moved to another style). Returns fixes made.
(defun ach:att-styles (ref defs / d n)
  (setq n 0)
  (foreach a (vlax-invoke ref 'GetAttributes)
    (if (and (setq d (assoc (strcase (vla-get-TagString a)) defs))
             (nth 4 d)
             (/= (strcase (vla-get-StyleName a)) (strcase (nth 4 d))))
      (if (not (vl-catch-all-error-p (vl-catch-all-apply 'vla-put-StyleName (list a (nth 4 d)))))
        (setq n (1+ n)))))
  n)

;; Is a style's font file available (support path, Windows or per-user fonts)?
(defun ach:font-found-p (ff / nm)
  (if (and ff (/= ff ""))
    (progn
      (setq nm (strcat (vl-filename-base ff) (cond ((vl-filename-extension ff)) (""))))
      (or (findfile ff)
          (and (getenv "WINDIR") (findfile (strcat (getenv "WINDIR") "\\Fonts\\" nm)))
          (and (getenv "LOCALAPPDATA")
               (findfile (strcat (getenv "LOCALAPPDATA") "\\Microsoft\\Windows\\Fonts\\" nm)))))))

;; Check (and if broken, repair) one text style. Returns a summary string.
;; Broken = no TrueType face and the font file can't be found -> AutoCAD
;; would draw it with the FONTALT fallback; then it is set to *ach:text-font*.
(defun ach:check-style (doc sname / st ff tf b i cs pf r)
  (setq st (vl-catch-all-apply 'vla-Item (list (vla-get-TextStyles doc) sname)))
  (if (vl-catch-all-error-p st)
    (strcat sname " (style missing!)")
    (progn
      (setq ff (vla-get-fontFile st))
      (setq r (vl-catch-all-apply 'vla-GetFont (list st 'tf 'b 'i 'cs 'pf)))
      (if (vl-catch-all-error-p r) (setq tf ""))
      (cond
        ((and (= (type tf) 'STR) (/= tf ""))
         (strcat sname " (" tf (if (ach:font-found-p ff) "" ", font file not found!") ")"))
        ((ach:font-found-p ff) (strcat sname " (" ff ")"))
        ((not (vl-catch-all-error-p
                (vl-catch-all-apply 'vla-SetFont
                  (list st *ach:text-font* :vlax-false :vlax-false 0 34))))
         (strcat sname " (font '" ff "' missing - repaired to " *ach:text-font* ")"))
        (T (strcat sname " (font '" ff "' missing!)"))))))

;; Rotated insert: put its attributes back where the unrotated symbol has
;; them, upright on the page (labels never turn with the symbol).
(defun ach:upright-atts (ref defs / d pt)
  (foreach a (vlax-invoke ref 'GetAttributes)
    (if (setq d (assoc (strcase (vla-get-TagString a)) defs))
      (progn
        (setq pt (ach:local->world ref (nth 2 d) 0.0))
        (vla-put-Rotation a (nth 3 d))
        (vla-put-Alignment a (nth 1 d))
        (if (= (nth 1 d) acAlignmentLeft)
          (vlax-put a 'InsertionPoint pt)
          (vlax-put a 'TextAlignmentPoint pt))))))

;; Top/bottom labels for one insert: department tag centred above the
;; symbol (baseline Center), weight tag centred below it (Top-Center), with a
;; clear gap, in page orientation. EXT = (ach:block-extents blk); the
;; crosshair of a rotated symbol never reaches past its unrotated extents.
(defun ach:topbottom-atts (ref ext / cx ytop ybot gap tag)
  (if ext
    (progn
      (setq cx   (/ (+ (car (car ext)) (car (cadr ext))) 2.0)
            gap  (* *ach:tb-gap-ratio* (/ (- (cadr (cadr ext)) (cadr (car ext))) 2.0))
            ytop (+ (cadr (cadr ext)) gap)
            ybot (- (cadr (car ext)) gap))
      (foreach a (vlax-invoke ref 'GetAttributes)
        (setq tag (strcase (vla-get-TagString a)))
        (cond
          ((= tag (strcase *ach:tag-dept*))
           ;; Center = baseline centre (Bottom-Center would sit on the
           ;; descender line and leave a larger gap than below)
           (vla-put-Alignment a acAlignmentCenter)
           (vlax-put a 'TextAlignmentPoint (ach:local->world ref (list cx ytop) 0.0)))
          ((= tag (strcase *ach:tag-load*))
           (vla-put-Alignment a acAlignmentTopCenter)
           (vlax-put a 'TextAlignmentPoint (ach:local->world ref (list cx ybot) 0.0))))))))

;; Colour + xdata on the insert in one entmod.
(defun ach:tag-insert (ename colspec row / ed xd)
  (setq ed (entget ename))
  (setq ed (vl-remove-if '(lambda (p) (member (car p) '(62 420 430))) ed))
  (setq ed (append ed
                   (vl-remove-if-not '(lambda (p) (member (car p) '(62 420))) colspec)))
  (setq xd (list -3 (list *ach:xdata-app*
                          (cons 1000 (ach:get row "source"))
                          (cons 1000 (ach:kind row))
                          (cons 1000 (ach:get row "flying_frame_id"))
                          (cons 1040 (ach:num row "weight_kg")))))
  (entmod (append ed (list xd)))
  (entupd ename))

;;; =================== plain AutoLISP engine (AutoCAD for Mac) ==============
(setq *ach:stage* "plain AutoLISP engine (AutoCAD for Mac)")
;; The same jobs as the ActiveX helpers above, done with tblsearch / entget /
;; entmod / entmake / command, which AutoCAD for Mac supports. Used when
;; ActiveX is missing, or on Windows with (setq *ach:force-engine* "lisp").
;; Blocks are passed around by name, inserts by entity name.

;; Replace (or add) DXF pairs in an entget list.
(defun ach:l-put (ed pairs)
  (foreach p pairs
    (setq ed (if (assoc (car p) ed)
               (subst p (assoc (car p) ed) ed)
               (append ed (list p)))))
  ed)

;; Change only the given groups. A partial list (-1 + changed pairs) is
;; used on purpose: entmod with the full entget list of an ATTRIB made by
;; entmake loses its style, justification and alignment point.
(defun ach:l-mod (e pairs) (entmod (cons (cons -1 e) pairs)))

;; ActiveX AcAlignment number <-> DXF 72 (horizontal) + 74 (vertical) of
;; ATTDEF / ATTRIB. 0 Left 1 Center 2 Right 3 Aligned 4 Middle 5 Fit,
;; 6-8 Top L/C/R, 9-11 Middle L/C/R, 12-14 Bottom L/C/R.
(defun ach:l-align (ed / h v)
  (setq h (cond ((cdr (assoc 72 ed))) (0))
        v (cond ((cdr (assoc 74 ed))) (0)))
  (cond ((= v 3) (+ 6 h)) ((= v 2) (+ 9 h)) ((= v 1) (+ 12 h)) (T h)))

(defun ach:l-align-codes (al)
  (cond ((< al 6)  (list (cons 72 al) (cons 74 0)))
        ((< al 9)  (list (cons 72 (- al 6)) (cons 74 3)))
        ((< al 12) (list (cons 72 (- al 9)) (cons 74 2)))
        (T         (list (cons 72 (- al 12)) (cons 74 1)))))

;; Anchor point: insertion point (10) for Left text, alignment point (11) otherwise.
(defun ach:l-anchor (ed)
  (if (= (ach:l-align ed) 0) (cdr (assoc 10 ed)) (cdr (assoc 11 ed))))

;; Set justification + anchor point of one attribute.
(defun ach:l-set-align (e al pt)
  (ach:l-mod e (append (ach:l-align-codes al)
                       (list (cons (if (= al 0) 10 11) pt)))))

;; ---------- blocks
(defun ach:l-block-ents (bname / e out)
  (setq e (cdr (assoc -2 (tblsearch "BLOCK" bname))))
  (while e (setq out (cons e out) e (entnext e)))
  (reverse out))

(defun ach:l-block-origin (bname / d)
  (if (setq d (tblsearch "BLOCK" bname)) (cdr (assoc 10 d)) '(0.0 0.0 0.0)))

(defun ach:l-find-block (/ found names unames d)
  (setq names (cons *ach:block-name* *ach:block-aliases*))
  (foreach n names
    (if (and (not found) (setq d (tblsearch "BLOCK" n)))
      (setq found (cdr (assoc 2 d)))))
  (if (not found)
    (progn
      (setq unames (mapcar 'strcase names)
            d      (tblnext "BLOCK" T))
      (while (and d (not found))
        (if (and (= 0 (logand 4 (cdr (assoc 70 d))))
                 (member (strcase (cdr (assoc 2 d))) unames))
          (setq found (cdr (assoc 2 d))))
        (setq d (tblnext "BLOCK")))))
  found)

;; BLOCK_RECORD of a block (holds the block's insert units in group 70).
(defun ach:l-block-record (bname / e ed)
  (if (setq e (tblobjname "BLOCK" bname))
    (progn (setq ed (entget e))
           (if (= (cdr (assoc 0 ed)) "BLOCK_RECORD") e (cdr (assoc 330 ed))))))

(defun ach:l-block-units (bname / r)
  (cond ((and (setq r (ach:l-block-record bname)) (cdr (assoc 70 (entget r)))))
        (0)))

;; Define the block from the DWG (-INSERT name=file, then cancel before the
;; insertion point, so only the definition stays). Returns the name or nil.
(defun ach:l-load-block-file (path / bname r)
  (setq bname (if (tblsearch "BLOCK" *ach:block-name*) (vl-filename-base path) *ach:block-name*))
  (setq r (vl-catch-all-apply
            '(lambda () (command "_.-INSERT" (strcat bname "=" path)) (command))
            nil))
  (if (and (not (vl-catch-all-error-p r)) (tblsearch "BLOCK" bname))
    (progn
      (if (= (ach:l-block-units bname) 0)
        (vl-catch-all-apply 'ach:l-mod
          (list (ach:l-block-record bname) (list (cons 70 *ach:block-default-units*)))))
      (setenv "ACHOISTS_BlockFile" path)
      bname)
    (progn (princ (strcat "\nACHOISTS: cannot insert " path)) nil)))

(defun ach:l-fills-byblock (bname / n ed)
  (setq n 0)
  (foreach e (ach:l-block-ents bname)
    (setq ed (entget e))
    (if (member (cdr (assoc 0 ed)) '("HATCH" "SOLID" "TRACE"))
      (progn
        (setq n (1+ n))
        (if (or (/= (cdr (assoc 62 ed)) 0) (assoc 420 ed) (assoc 430 ed))
          (progn
            (setq ed (vl-remove-if '(lambda (p) (member (car p) '(420 430))) ed))
            (entmod (if (assoc 62 ed)
                      (subst '(62 . 0) (assoc 62 ed) ed)
                      ;; no 62 = ByLayer: add it right after the layer
                      (apply 'append
                             (mapcar '(lambda (p) (if (= (car p) 8) (list p '(62 . 0)) (list p)))
                                     ed)))))))))
  n)

(defun ach:l-attdef-eds (bname)
  (vl-remove-if-not '(lambda (ed) (= (cdr (assoc 0 ed)) "ATTDEF"))
                    (mapcar 'entget (ach:l-block-ents bname))))

(defun ach:l-block-tags (bname)
  (mapcar '(lambda (ed) (cdr (assoc 2 ed))) (ach:l-attdef-eds bname)))

;; Same list as ach:block-attdefs.
(defun ach:l-block-attdefs (bname / org pt out)
  (setq org (ach:l-block-origin bname))
  (foreach ed (ach:l-attdef-eds bname)
    (setq pt (ach:l-anchor ed))
    (setq out (cons (list (strcase (cdr (assoc 2 ed))) (ach:l-align ed)
                          (list (- (car pt) (car org)) (- (cadr pt) (cadr org)))
                          (cdr (assoc 50 ed))
                          (cdr (assoc 7 ed)))
                    out)))
  out)

;; ---------- geometry extents (no GetBoundingBox without ActiveX)
;; Points of a CCW arc from A1 to A2 (radians): ends + quadrant points.
(defun ach:l-arc-pts (c r a1 a2 / pts k a)
  (setq a1  (rem a1 (* 2.0 pi)))
  (if (< a1 0.0) (setq a1 (+ a1 (* 2.0 pi))))
  (setq a2  (rem a2 (* 2.0 pi)))
  (if (< a2 0.0) (setq a2 (+ a2 (* 2.0 pi))))
  (if (<= a2 a1) (setq a2 (+ a2 (* 2.0 pi))))
  (setq pts (list (polar c a1 r) (polar c a2 r)) k 0)
  (repeat 8
    (setq a (* k (/ pi 2.0)) k (1+ k))
    (if (and (> a a1) (< a a2)) (setq pts (cons (polar c a r) pts))))
  pts)

;; Points of one polyline segment P1 -> P2 with bulge B.
(defun ach:l-bulge-pts (p1 p2 b / th r c tmp)
  (if (or (not b) (equal b 0.0 1e-12) (equal p1 p2 1e-12))
    (list p1 p2)
    (progn
      (if (< b 0.0) (setq tmp p1 p1 p2 p2 tmp b (- b)))
      (setq th (* 4.0 (atan b))
            r  (/ (distance p1 p2) (* 2.0 (sin (/ th 2.0))))
            c  (polar p1 (+ (angle p1 p2) (- (/ pi 2.0) (/ th 2.0))) r))
      (ach:l-arc-pts c r (angle c p1) (angle c p2)))))

;; Closed or open vertex list ((pt . bulge) ...) -> points.
(defun ach:l-vertex-pts (verts closed / pts i n)
  (setq n (length verts) i 0)
  (repeat (if closed n (max 0 (1- n)))
    (setq pts (append (ach:l-bulge-pts (car (nth i verts))
                                       (car (nth (rem (1+ i) n) verts))
                                       (cdr (nth i verts)))
                      pts)
          i (1+ i)))
  (if (= n 1) (list (car (car verts))) pts))

;; Boundary points of a HATCH (polyline paths with bulges, line and arc edges).
(defun ach:l-hatch-pts (ed / l pts npath flag hasb cnt verts v b et c r)
  (if (setq l (member (assoc 91 ed) ed))
    (progn
      (setq npath (cdr (car l)) l (cdr l))
      (repeat npath
        (if (setq l (member (assoc 92 l) l))
          (progn
            (setq flag (cdr (car l)) l (cdr l))
            (if (= 2 (logand flag 2))
              (progn                    ; polyline path
                (setq hasb (cdr (assoc 72 l))
                      l    (member (assoc 93 l) l)
                      cnt  (cdr (car l)) l (cdr l) verts nil)
                (repeat cnt
                  (setq l (member (assoc 10 l) l) v (cdr (car l)) l (cdr l) b 0.0)
                  (if (and (= hasb 1) (= (car (car l)) 42)) (setq b (cdr (car l)) l (cdr l)))
                  (setq verts (cons (cons v b) verts)))
                (setq pts (append (ach:l-vertex-pts (reverse verts) T) pts)))
              (progn                    ; edge path
                (setq l (member (assoc 93 l) l) cnt (cdr (car l)) l (cdr l))
                (repeat cnt
                  (setq l (member (assoc 72 l) l) et (cdr (car l)) l (cdr l))
                  (cond
                    ((= et 2)           ; arc: angles in degrees
                     (setq c (cdr (assoc 10 l)) r (cdr (assoc 40 l)))
                     (setq pts (append (if (= (cdr (assoc 73 l)) 1)
                                         (ach:l-arc-pts c r (* pi (/ (cdr (assoc 50 l)) 180.0))
                                                            (* pi (/ (cdr (assoc 51 l)) 180.0)))
                                         ;; clockwise: take the whole circle
                                         (list (polar c 0.0 r) (polar c (/ pi 2.0) r)
                                               (polar c pi r) (polar c (* 1.5 pi) r)))
                                       pts)))
                    (T (setq pts (cons (cdr (assoc 10 l)) pts))
                       (if (and (= et 1) (assoc 11 l)) (setq pts (cons (cdr (assoc 11 l)) pts)))))))))))))
  pts)

(defun ach:l-ent-pts (ed / typ c r v verts l tb rot ip)
  (setq typ (cdr (assoc 0 ed)))
  (cond
    ((= typ "LINE") (list (cdr (assoc 10 ed)) (cdr (assoc 11 ed))))
    ((= typ "CIRCLE")
     (setq c (cdr (assoc 10 ed)) r (cdr (assoc 40 ed)))
     (list (list (- (car c) r) (- (cadr c) r)) (list (+ (car c) r) (+ (cadr c) r))))
    ((= typ "ARC")
     (ach:l-arc-pts (cdr (assoc 10 ed)) (cdr (assoc 40 ed)) (cdr (assoc 50 ed)) (cdr (assoc 51 ed))))
    ((= typ "LWPOLYLINE")
     (setq l ed)
     (while (setq l (member (assoc 10 l) l))
       (setq v (cdr (car l)) l (cdr l) c 0.0)
       ;; this vertex's bulge (42) sits before the next 10
       (while (and l (/= (car (car l)) 10))
         (if (= (car (car l)) 42) (setq c (cdr (car l))))
         (setq l (cdr l)))
       (setq verts (cons (cons v c) verts)))
     (ach:l-vertex-pts (reverse verts) (= 1 (logand 1 (cdr (assoc 70 ed))))))
    ((member typ '("SOLID" "TRACE"))
     (mapcar '(lambda (g) (cdr (assoc g ed))) '(10 11 12 13)))
    ((member typ '("POINT" "VERTEX")) (list (cdr (assoc 10 ed))))
    ((= typ "HATCH") (ach:l-hatch-pts ed))
    ((= typ "ELLIPSE")
     (setq c (cdr (assoc 10 ed)) v (cdr (assoc 11 ed))
           r (distance '(0.0 0.0) (list (car v) (cadr v))))
     (list (list (- (car c) r) (- (cadr c) r)) (list (+ (car c) r) (+ (cadr c) r))))
    ((= typ "TEXT")
     (if (setq tb (textbox ed))
       (progn
         (setq rot (cdr (assoc 50 ed)) ip (cdr (assoc 10 ed)))
         (mapcar '(lambda (p) (list (+ (car ip) (- (* (car p) (cos rot)) (* (cadr p) (sin rot))))
                                    (+ (cadr ip) (+ (* (car p) (sin rot)) (* (cadr p) (cos rot))))))
                 (list (car tb) (cadr tb) (list (car (car tb)) (cadr (cadr tb)))
                       (list (car (cadr tb)) (cadr (car tb))))))))))

;; Same result as ach:block-extents.
(defun ach:l-block-extents (bname / org lo hi)
  (setq org (ach:l-block-origin bname))
  (foreach e (ach:l-block-ents bname)
    (foreach p (vl-remove nil (ach:l-ent-pts (entget e)))
      (setq lo (if lo (list (min (car lo) (car p)) (min (cadr lo) (cadr p))) (list (car p) (cadr p)))
            hi (if hi (list (max (car hi) (car p)) (max (cadr hi) (cadr p))) (list (car p) (cadr p))))))
  (if (and lo hi)
    (list (list (- (car lo) (car org)) (- (cadr lo) (cadr org)))
          (list (- (car hi) (car org)) (- (cadr hi) (cadr org))))))

;; ---------- text style (check only; the Mac engine does not repair fonts)
(defun ach:l-check-style (sname / d e xd tf ff)
  (if (not (setq d (tblsearch "STYLE" sname)))
    (strcat sname " (style missing!)")
    (progn
      (setq ff (cond ((cdr (assoc 3 d))) ("")))
      (setq e  (tblobjname "STYLE" sname)
            xd (cdr (assoc -3 (entget e '("ACAD"))))
            tf (cdr (assoc 1000 (cdr (assoc "ACAD" xd)))))
      (cond
        ((and tf (/= tf ""))
         (strcat sname " (" tf
                 (if (or (ach:mac-p) (ach:font-found-p ff)) "" ", font file not found!") ")"))
        ((ach:font-found-p ff) (strcat sname " (" ff ")"))
        (T (strcat sname " (font '" ff "' not found - check the style)"))))))

;; ---------- layer
(defun ach:l-ensure-layer (name / e ed fl)
  (if (not (tblsearch "LAYER" name))
    (entmake (list '(0 . "LAYER") '(100 . "AcDbSymbolTableRecord") '(100 . "AcDbLayerTableRecord")
                   (cons 2 name) '(70 . 0) (cons 62 *ach:layer-color*) '(6 . "Continuous"))))
  (if (setq e (tblobjname "LAYER" name))
    (progn
      (setq ed (entget e)
            fl (logand (cdr (assoc 70 ed)) (~ 4)))                  ; unlock
      (if (/= (strcase (getvar "CLAYER")) (strcase name))
        (setq fl (logand fl (~ 1))))                                ; thaw
      (entmod (ach:l-put ed (list (cons 70 fl) (cons 62 (abs (cdr (assoc 62 ed))))))))) ; on
  name)

;; ---------- previous inserts
(defun ach:l-previous-inserts (bname / ss i e out)
  (if (setq ss (ssget "_X" (list (cons 0 "INSERT") (list -3 (list *ach:xdata-app*)))))
    (progn (setq i 0)
           (repeat (sslength ss) (setq out (cons (ssname ss i) out) i (1+ i)))))
  (if (and bname (setq ss (ssget "_X" (list (cons 0 "INSERT") (cons 8 *ach:layer*)))))
    (progn
      (setq i 0)
      (repeat (sslength ss)
        (setq e (ssname ss i) i (1+ i))
        (if (and (= (strcase (cdr (assoc 2 (entget e)))) (strcase bname))
                 (not (member e out)))
          (setq out (cons e out))))))
  out)

;; ---------- inserts and attributes
;; Block point -> world: (p - origin) x scale, rotated by ROT, + insertion point.
(defun ach:l-xform (lp org ip sc rot / x y)
  (setq x (* (- (car lp) (car org)) sc)
        y (* (- (cadr lp) (cadr org)) sc))
  (list (+ (car ip) (- (* x (cos rot)) (* y (sin rot))))
        (+ (cadr ip) (+ (* x (sin rot)) (* y (cos rot))))
        (+ (caddr ip) (* (- (cond ((caddr lp)) (0.0)) (cond ((caddr org)) (0.0))) sc))))

;; ATTRIB entmake list for one ATTDEF of a block inserted at IP, SC, ROT.
(defun ach:l-attrib (d org ip sc rot / out g)
  ;; no subclass markers: with them entmake drops the style, justification
  ;; and alignment point of an ATTRIB
  (setq out (list '(0 . "ATTRIB") '(67 . 0)))
  (foreach g '(8 6 62 420 370 48 60)
    (if (assoc g d) (setq out (append out (list (assoc g d))))))
  (append out
          (list (cons 10 (ach:l-xform (cdr (assoc 10 d)) org ip sc rot))
                (cons 40 (* (cdr (assoc 40 d)) sc))
                (cons 1 (cdr (assoc 1 d)))
                (cons 50 (+ (cdr (assoc 50 d)) rot))
                (cons 41 (cdr (assoc 41 d)))
                (cons 51 (cdr (assoc 51 d)))
                (cons 7 (cdr (assoc 7 d)))
                (cons 71 (cdr (assoc 71 d)))
                (cons 72 (cdr (assoc 72 d)))
                (cons 11 (ach:l-xform (cdr (assoc 11 d)) org ip sc rot))
                '(210 0.0 0.0 1.0)
                (cons 2 (cdr (assoc 2 d)))
                (cons 70 (logand (cdr (assoc 70 d)) (~ 2)))
                '(73 . 0)
                (cons 74 (cdr (assoc 74 d))))))

;; Insert BNAME in model space with its attributes (default values).
;; Returns the INSERT's entity name, or nil.
(defun ach:l-insert (bname ip sc rot / org defs ok)
  (setq org  (ach:l-block-origin bname)
        defs (vl-remove-if '(lambda (ed) (= 2 (logand 2 (cdr (assoc 70 ed)))))
                           (ach:l-attdef-eds bname)))
  (setq ok (entmake (append (list '(0 . "INSERT") '(100 . "AcDbEntity") '(67 . 0)
                                  (cons 8 (getvar "CLAYER")) '(100 . "AcDbBlockReference"))
                            (if defs '((66 . 1)))
                            (list (cons 2 bname) (cons 10 ip)
                                  (cons 41 sc) (cons 42 sc) (cons 43 sc) (cons 50 rot)
                                  '(210 0.0 0.0 1.0)))))
  (if ok
    (progn
      (foreach d defs (if (not (entmake (ach:l-attrib d org ip sc rot))) (setq ok nil)))
      (if defs (if (not (entmake '((0 . "SEQEND") (100 . "AcDbEntity")))) (setq ok nil)))))
  (if ok (entlast)))

(defun ach:l-atts (ins / e ed out)
  (setq e (entnext ins))
  (while (and e (= (cdr (assoc 0 (setq ed (entget e)))) "ATTRIB"))
    (setq out (cons e out) e (entnext e)))
  (reverse out))

(defun ach:l-tag (a) (strcase (cdr (assoc 2 (entget a)))))

(defun ach:l-set-att (ins tag val / hit)
  (foreach a (ach:l-atts ins)
    (if (= (ach:l-tag a) (strcase tag))
      (progn (ach:l-mod a (list (cons 1 val))) (setq hit T))))
  hit)

(defun ach:l-att-styles (ins defs / d n)
  (setq n 0)
  (foreach a (ach:l-atts ins)
    (if (and (setq d (assoc (ach:l-tag a) defs))
             (nth 4 d)
             (/= (strcase (cdr (assoc 7 (entget a)))) (strcase (nth 4 d)))
             (ach:l-mod a (list (cons 7 (nth 4 d)))))
      (setq n (1+ n))))
  n)

;; Like ach:local->world, for an INSERT entity.
(defun ach:l-local->world (ins lp rot / ed ip x y)
  (setq ed (entget ins)
        ip (cdr (assoc 10 ed))
        x  (* (car lp) (cdr (assoc 41 ed)))
        y  (* (cadr lp) (cdr (assoc 42 ed))))
  (list (+ (car ip) (- (* x (cos rot)) (* y (sin rot))))
        (+ (cadr ip) (+ (* x (sin rot)) (* y (cos rot))))
        (caddr ip)))

(defun ach:l-upright-atts (ins defs / d)
  (foreach a (ach:l-atts ins)
    (if (setq d (assoc (ach:l-tag a) defs))
      (progn
        (ach:l-mod a (list (cons 50 (nth 3 d))))
        (ach:l-set-align a (nth 1 d) (ach:l-local->world ins (nth 2 d) 0.0))))))

(defun ach:l-topbottom-atts (ins ext / cx ytop ybot gap tag)
  (if ext
    (progn
      (setq cx   (/ (+ (car (car ext)) (car (cadr ext))) 2.0)
            gap  (* *ach:tb-gap-ratio* (/ (- (cadr (cadr ext)) (cadr (car ext))) 2.0))
            ytop (+ (cadr (cadr ext)) gap)
            ybot (- (cadr (car ext)) gap))
      (foreach a (ach:l-atts ins)
        (setq tag (ach:l-tag a))
        (cond
          ((= tag (strcase *ach:tag-dept*))
           (ach:l-set-align a 1 (ach:l-local->world ins (list cx ytop) 0.0)))   ; Center
          ((= tag (strcase *ach:tag-load*))
           (ach:l-set-align a 7 (ach:l-local->world ins (list cx ybot) 0.0)))))))) ; TopCenter

(defun ach:l-flip-atts (ins / ip ed al nal pt)
  (setq ip (cdr (assoc 10 (entget ins))))
  (foreach a (ach:l-atts ins)
    (setq ed  (entget a)
          al  (ach:l-align ed)
          nal (cdr (assoc al '((0 . 2) (2 . 0) (6 . 8) (8 . 6) (9 . 11) (11 . 9)
                               (12 . 14) (14 . 12) (1 . 1) (4 . 4) (7 . 7) (10 . 10) (13 . 13)))))
    (if nal
      (progn
        (setq pt (ach:l-anchor ed))
        (ach:l-set-align a nal (list (- (* 2.0 (car ip)) (car pt)) (cadr pt) (caddr pt)))))))

;;; ======================= engine switch (ActiveX / plain) =================
(setq *ach:stage* "engine switch (ActiveX / plain)")
(setq *ach:eng* nil)

;; "activex" or "lisp" for a run. REQ: "lisp" / "activex" / nil (= automatic).
(defun ach:engine (req / e)
  (setq e (cond (req) (*ach:force-engine*) ("auto")))
  (if (and (/= e "lisp") (ach:activex-p)) "activex" "lisp"))

(defun ach:ax-p () (/= *ach:eng* "lisp"))

(defun ach:x-undo-start (doc)
  (if (ach:ax-p) (vla-StartUndoMark doc) (command-s "_.UNDO" "_Begin")))
(defun ach:x-undo-end (doc)
  (if (ach:ax-p) (vla-EndUndoMark doc) (command-s "_.UNDO" "_End")))
(defun ach:x-regen (doc)
  (if (ach:ax-p) (vla-Regen doc acAllViewports) (command-s "_.REGENALL")))
(defun ach:x-find-block (doc)
  (if (ach:ax-p) (ach:find-block doc) (ach:l-find-block)))
(defun ach:x-load-block-file (doc ms path)
  (if (ach:ax-p) (ach:load-block-file doc ms path) (ach:l-load-block-file path)))
(defun ach:x-block (doc bname)
  (if (ach:ax-p) (vla-Item (vla-get-Blocks doc) bname) bname))
(defun ach:x-block-units (blk)
  (if (ach:ax-p) (vla-get-Units blk) (ach:l-block-units blk)))
(defun ach:x-fills-byblock (blk)
  (if (ach:ax-p) (ach:fills-byblock blk) (ach:l-fills-byblock blk)))
(defun ach:x-block-tags (blk)
  (if (ach:ax-p) (ach:block-tags blk) (ach:l-block-tags blk)))
(defun ach:x-block-extents (blk)
  (if (ach:ax-p) (ach:block-extents blk) (ach:l-block-extents blk)))
(defun ach:x-block-attdefs (blk)
  (if (ach:ax-p) (ach:block-attdefs blk) (ach:l-block-attdefs blk)))
(defun ach:x-check-style (doc sname)
  (if (ach:ax-p) (ach:check-style doc sname) (ach:l-check-style sname)))
(defun ach:x-ensure-layer (doc name)
  (if (ach:ax-p) (ach:ensure-layer doc name) (ach:l-ensure-layer name)))
(defun ach:x-previous-inserts (bname)
  (if (ach:ax-p) (ach:previous-inserts bname) (ach:l-previous-inserts bname)))
;; Returns the insert (VLA object or ename), or nil / an error object.
(defun ach:x-insert (ms bname pt sc rot)
  (if (ach:ax-p)
    (vl-catch-all-apply 'vla-InsertBlock
      (list ms (vlax-3d-point (car pt) (cadr pt) (caddr pt)) bname sc sc sc rot))
    (vl-catch-all-apply 'ach:l-insert (list bname pt sc rot))))
(defun ach:x-put-layer (ref lay)
  (if (ach:ax-p) (vla-put-Layer ref lay) (ach:l-mod ref (list (cons 8 lay)))))
(defun ach:x-set-att (ref tag val)
  (if (ach:ax-p) (ach:set-att ref tag val) (ach:l-set-att ref tag val)))
(defun ach:x-att-styles (ref defs)
  (if (ach:ax-p) (ach:att-styles ref defs) (ach:l-att-styles ref defs)))
(defun ach:x-upright-atts (ref defs)
  (if (ach:ax-p) (ach:upright-atts ref defs) (ach:l-upright-atts ref defs)))
(defun ach:x-topbottom-atts (ref ext)
  (if (ach:ax-p) (ach:topbottom-atts ref ext) (ach:l-topbottom-atts ref ext)))
(defun ach:x-flip-atts (ref)
  (if (ach:ax-p) (ach:flip-atts ref) (ach:l-flip-atts ref)))
(defun ach:x-ename (ref)
  (if (ach:ax-p) (vlax-vla-object->ename ref) ref))


;;; ======================== label side (auto flip) =========================

;; Normalise a layout value -> "side" or "topbottom".
(defun ach:norm-layout (s)
  (if (member (ach:clean-key (if (= (type s) 'STR) s ""))
              '("topbottom" "tb" "top" "bottom" "topandbottom"))
    "topbottom"
    "side"))

;; Normalise a per-source value -> "default" "auto" "right" "left" "topbottom".
(defun ach:norm-mode (s / k)
  (setq k (ach:clean-key (if (= (type s) 'STR) s "")))
  (cond ((member k '("auto" "autolr" "side")) "auto")
        ((member k '("left" "right")) k)
        ((member k '("topbottom" "tb" "top" "bottom" "topandbottom")) "topbottom")
        (T "default")))

;; Rotate the X/Y of every row about 0,0 by DEG degrees (CCW positive,
;; like ROTATE). Z and everything else unchanged.
(defun ach:rotate-rows (rows deg / a c sn x y)
  (if (or (not (numberp deg)) (equal deg 0.0 1e-12))
    rows
    (progn
      (setq a (* pi (/ deg 180.0)) c (cos a) sn (sin a))
      (mapcar '(lambda (row)
                 (setq x (ach:num row "x_m") y (ach:num row "y_m"))
                 (subst (cons "y_m" (rtos (+ (* x sn) (* y c)) 2 10)) (assoc "y_m" row)
                        (subst (cons "x_m" (rtos (- (* x c) (* y sn)) 2 10)) (assoc "x_m" row)
                               row)))
              rows))))

(defun ach:frame-key (row / key)
  (setq key (ach:get row "flying_frame_id"))
  (if (= key "") (strcat (ach:get row "source") "|" (ach:get row "y_m")) key))

;; Label plan, computed on the page positions (after rotation):
;; ((row . "right"|"left"|"topbottom") ...), plus the number of top/bottom
;; rows that fell back to left/right -> (plan . nfallback).
;; Per-source value (sides): "default"/missing = LAYOUT, "auto" = mirror the
;; lower-X hoist of a close front/rear pair, "right", "left", "topbottom"
;; (forced, no fallback).
(defun ach:label-plan (rows sides scale layout / frames key e f r mode out
                       dx dy pair auto-side nfb res)
  (foreach row rows
    (setq key (ach:frame-key row))
    (if (setq e (assoc key frames))
      (setq frames (subst (cons key (cons row (cdr e))) e frames))
      (setq frames (cons (list key row) frames))))
  (setq nfb 0)
  (foreach row rows
    (setq mode (ach:norm-mode (cdr (assoc (ach:get row "source") sides))))
    ;; front/rear partner offsets on the page
    (setq f nil r nil dx nil dy nil)
    (if (member (ach:kind row) '("front" "rear"))
      (foreach x (cdr (assoc (ach:frame-key row) frames))
        (if (= (ach:kind x) "front") (setq f x))
        (if (= (ach:kind x) "rear") (setq r x))))
    (if (and f r)
      (setq dx (- (ach:num f "x_m") (ach:num r "x_m"))
            dy (- (ach:num f "y_m") (ach:num r "y_m"))))
    (setq auto-side
      (if (and dx
               (< (abs dy) (* *ach:flip-clearance-m* scale))
               ;; this row is the lower-X pick of the pair
               (if (eq row f) (< dx 0.0) (>= dx 0.0)))
        "left" "right"))
    (setq res
      (cond
        ((member mode '("left" "right" "topbottom")) mode)
        ((= mode "auto") auto-side)
        ((/= layout "topbottom") auto-side)
        ((and *ach:tb-fallback* dx
              (< (abs dx) (* *ach:tb-clear-x-m* scale))
              (< (abs dy) (* *ach:tb-clear-y-m* scale)))
         (setq nfb (1+ nfb))
         auto-side)
        (T "topbottom")))
    (setq out (cons (cons row res) out)))
  (cons (reverse out) nfb))

;;; ============================ core command ===============================
(setq *ach:stage* "core command")

(defun achoists-run (csvpath singles colspec dept suffix deleteold)
  (achoists-run-ex csvpath singles colspec dept suffix deleteold nil))

;; Same with an explicit label layout: "side" or "topbottom".
(defun achoists-run-layout (csvpath singles colspec dept suffix deleteold layout)
  (achoists-run-ex csvpath singles colspec dept suffix deleteold
                   (list (cons "layout" layout))))

(defun achoists-run-ex (csvpath singles colspec dept suffix deleteold opts
                        / *error* acad doc ms data keys rows names meta bad
                          sel factor scale sides bfile bname blk bunits
                          sc nfill tags old removed flips placed failed ref
                          x y z w sv-names sv-vals undo-open lay msg missing
                          layout tbs ext defs plan nfb rot rotsym rrad
                          sfix stxt)
  (setq *ach:eng* (ach:engine (cdr (assoc "engine" opts))))
  (setq sv-names '("CMDECHO" "OSMODE" "ATTREQ" "ATTDIA")
        sv-vals  (mapcar 'getvar sv-names))
  (defun *error* (m)
    (mapcar 'setvar sv-names sv-vals)
    (if undo-open (ach:x-undo-end doc))
    (if (not (member m '("Function cancelled" "quit / exit abort")))
      (princ (strcat "\nACHOISTS error: " m)))
    (princ))

  (if (ach:ax-p)
    (setq acad (vlax-get-acad-object)
          doc  (vla-get-ActiveDocument acad)
          ms   (vla-get-ModelSpace doc)))
  (cond
    ;; ---------- validate input
    ((not (and csvpath (findfile csvpath)))
     (cons nil (strcat "CSV not found: " (vl-princ-to-string csvpath))))
    ((not (setq data (ach:read-csv csvpath)))
     (cons nil (strcat "Cannot read CSV: " csvpath)))
    ((progn (setq keys (car data) rows (cadr data))
            (setq missing (vl-remove-if '(lambda (k) (member k keys))
                                        '("source" "pick_kind" "x_m" "y_m" "z_m" "weight_kg"))))
     (cons nil (strcat "CSV is missing column(s): " (ach:join missing ", "))))
    ((null rows) (cons nil "CSV has no data rows."))
    (T
     (setq data  (ach:sources rows)
           names (car data)
           meta  (cadr data))
     (setq bad (vl-remove-if '(lambda (s) (ach:can-single meta s)) singles))
     (setq factor (cdr (assoc "factor" opts)))
     (if (not factor) (setq factor (ach:factor-from-insunits)))
     (setq scale (cdr (assoc "scale" opts)))
     (if (not (and (numberp scale) (> scale 0.0))) (setq scale *ach:symbol-scale*))
     (setq sides (cdr (assoc "sides" opts)))
     (setq layout (ach:norm-layout (cond ((cdr (assoc "layout" opts))) (*ach:label-layout*))))
     (setq rot (cdr (assoc "rotation" opts)))
     (if (= (type rot) 'STR) (setq rot (distof rot 2)))
     (if (not (numberp rot)) (setq rot 0.0))
     (setq rot (float rot)
           rotsym (if (cdr (assoc "rotate-symbols" opts)) T nil)
           rrad (if rotsym (* pi (/ rot 180.0)) 0.0))
     (setq colspec (ach:color-spec colspec))
     (if (not dept) (setq dept *ach:default-dept*))
     (if (not suffix) (setq suffix *ach:default-suffix*))
     (cond
       (bad (cons nil (strcat "No single pick in ArrayCalc for: " (ach:join bad ", "))))
       ((not factor)
        (cons nil "Drawing units are unitless (INSUNITS = 0): pass (\"factor\" . units-per-metre)."))
       ((null (setq sel (ach:filter-rows rows singles)))
        (cons nil "Nothing to place with this selection."))
       (T
        (setvar "CMDECHO" 0) (setvar "OSMODE" 0)
        (setvar "ATTREQ" 0)  (setvar "ATTDIA" 0)
        (ach:x-undo-start doc) (setq undo-open T)

        ;; ---------- block definition
        (setq bname (ach:x-find-block doc))
        (if (not bname)
          (progn
            (setq bfile (cdr (assoc "blockfile" opts)))
            (if (not (and bfile (findfile bfile))) (setq bfile (ach:find-block-file csvpath)))
            (if bfile (setq bname (ach:x-load-block-file doc ms bfile)))))
        (if (not bname)
          (progn
            (mapcar 'setvar sv-names sv-vals)
            (ach:x-undo-end doc) (setq undo-open nil)
            (cons nil (strcat "Hoist block '" *ach:block-name* "' is not in the drawing and "
                              *ach:block-file* " was not found.")))
          (progn
            (setq blk    (ach:x-block doc bname)
                  bunits (ach:x-block-units blk))
            (if (not (ach:metres-per-unit bunits)) (setq bunits *ach:block-default-units*))
            ;; block units -> drawing units, times user symbol scale
            (setq sc (* (ach:metres-per-unit bunits) factor scale))
            (setq nfill (if *ach:fill-byblock* (ach:x-fills-byblock blk) 0))
            (setq tags (ach:x-block-tags blk))
            (setq ext  (ach:x-block-extents blk)
                  defs (ach:x-block-attdefs blk)
                  sfix 0)
            ;; text style(s) of the attribute definitions: check / repair font
            (setq stxt '())
            (foreach d defs
              (if (and (nth 4 d) (not (assoc (strcase (nth 4 d)) stxt)))
                (setq stxt (cons (cons (strcase (nth 4 d)) (ach:x-check-style doc (nth 4 d))) stxt))))

            ;; ---------- layer, xdata app, old inserts
            (setq lay (ach:x-ensure-layer doc *ach:layer*))
            (regapp *ach:xdata-app*)
            (setq old (ach:x-previous-inserts bname) removed 0)
            (if deleteold
              (foreach e old (if (entdel e) (setq removed (1+ removed)))))

            ;; ---------- place
            (setq sel   (ach:rotate-rows sel rot)
                  plan  (ach:label-plan sel sides scale layout)
                  nfb   (cdr plan)
                  plan  (car plan)
                  flips (vl-remove-if-not '(lambda (p) (= (cdr p) "left")) plan)
                  tbs   (vl-remove-if-not '(lambda (p) (= (cdr p) "topbottom")) plan)
                  placed 0 failed 0)
            (foreach row sel
              (setq x (* (ach:num row "x_m") factor)
                    y (* (ach:num row "y_m") factor)
                    z (* (ach:num row "z_m") factor)
                    w (ach:num row "weight_kg"))
              (setq ref (ach:x-insert ms bname (list x y z) sc rrad))
              (if (or (not ref) (vl-catch-all-error-p ref))
                (setq failed (1+ failed))
                (progn
                  (ach:x-put-layer ref *ach:layer*)
                  (ach:x-set-att ref *ach:tag-dept* dept)
                  (ach:x-set-att ref *ach:tag-load* (ach:fmt-load w suffix))
                  (setq sfix (+ sfix (ach:x-att-styles ref defs)))
                  (if (/= rrad 0.0) (ach:x-upright-atts ref defs))
                  (cond ((= (cdr (assoc row plan)) "topbottom") (ach:x-topbottom-atts ref ext))
                        ((= (cdr (assoc row plan)) "left") (ach:x-flip-atts ref)))
                  (ach:tag-insert (ach:x-ename ref) colspec row)
                  (setq placed (1+ placed)))))

            (ach:x-regen doc)
            (ach:x-undo-end doc) (setq undo-open nil)
            (mapcar 'setvar sv-names sv-vals)

            ;; ---------- summary
            (setq msg
              (strcat
                "Placed " (itoa placed) " hoist(s)"
                (if (> failed 0) (strcat ", FAILED " (itoa failed)) "")
                "\nCSV: " csvpath
                "\n\nUnits: " (ach:unit-name (getvar "INSUNITS"))
                ", 1 m = " (rtos factor 2 4) " drawing units"
                "\nSymbol scale: " (rtos scale 2 3) "  (insert scale " (rtos sc 2 4) ")"
                "\nInsertion Z = ArrayCalc hoist height"
                "\nRotation: " (rtos rot 2 2) " deg about 0,0"
                (if (equal rot 0.0 1e-9) ""
                  (if rotsym "  (symbols rotated, labels upright)" "  (symbols upright)"))
                "\n\nBlock: " bname "   layer: " *ach:layer*
                "\nTags: " *ach:tag-dept* " = \"" dept "\", "
                *ach:tag-load* " = weight + \"" suffix "\""
                (if (and (member (strcase *ach:tag-dept*) (mapcar 'strcase tags))
                         (member (strcase *ach:tag-load*) (mapcar 'strcase tags)))
                  ""
                  (strcat "\n!! Block attribute tags are: " (ach:join tags ", ")
                          " - set *ach:tag-dept* / *ach:tag-load* at the top of the .lsp"))
                "\nText style: " (ach:join (mapcar 'cdr (reverse stxt)) ", ")
                (if (> sfix 0) (strcat "  (" (itoa sfix) " attribute style(s) fixed)") "")
                "\nSolid colour: " (ach:color-text colspec)
                (if (> nfill 0) "" "  (!! block has no HATCH/SOLID fill)")
                "\nLabel layout: " (if (= layout "topbottom") "top / bottom" "left / right")
                "\nLabels top/bottom: " (itoa (length tbs))
                ", mirrored left: " (itoa (length flips))
                (if (> nfb 0)
                  (strcat "\n(" (itoa nfb) " hoist(s) in close front/rear pairs kept left/right)")
                  "")
                "\n\nSingle-point: "
                (if singles (ach:join singles ", ") "none (all front + rear)")
                "\nPrevious inserts: " (itoa (length old))
                (if deleteold (strcat ", deleted " (itoa removed)) " (kept)")))
            (cons T msg))))))))

;;; ============================ dialog (DCL) ===============================
(setq *ach:stage* "dialog (DCL)")

(setq *ach:side-modes*  '("default" "auto" "right" "left" "topbottom"))
(setq *ach:side-labels* '("as layout" "auto L/R" "right" "left" "top/bottom"))

;; edit_width: the Mac edit_box tile does not list it (Mac DCL reference,
;; edit_box), so on a Mac the edit box just fills its row.
(defun ach:dcl-ew (n)
  (if (ach:mac-p) "" (strcat "edit_width = " (itoa n) "; ")))

(defun ach:write-dcl (n / path f i)
  (setq path (vl-filename-mktemp "achoists" nil ".dcl"))
  (setq f (open path "w"))
  (foreach l
    '("achoists : dialog {"
      "  label = \"Place ArrayCalc Hoists\";"
      "  : text { key = \"csv\"; width = 90; }"
      "  : text { key = \"info\"; width = 90; }"
      "  : boxed_column {"
      "    label = \"Flown sources  (default = front + rear picks; tick = single-point hang)\";"
      "    : row {"
      "      : text { label = \"Source\"; width = 48; }"
      "      : text { label = \"Hang\"; width = 16; }"
      "      : text { label = \"Labels\"; width = 18; }"
      "    }")
    (write-line l f))
  (setq i 1)
  (repeat n
    (write-line
      (strcat "    : row { : text { key = \"n" (itoa i) "\"; width = 48; }"
              " : toggle { key = \"s" (itoa i) "\"; label = \"Single-point\"; width = 16; }"
              " : popup_list { key = \"p" (itoa i) "\"; width = 18; } }")
      f)
    (setq i (1+ i)))
  (foreach l
    (list "  }"
      "  : boxed_radio_row {"
      "    key = \"layout\";"
      "    label = \"Label layout  (sources set to 'as layout')\";"
      "    : radio_button { key = \"lay_side\"; label = \"Left / right  (auto-mirror close pairs)\"; }"
      "    : radio_button { key = \"lay_tb\"; label = \"Top / bottom  (name above, weight below)\"; }"
      "  }"
      "  : boxed_column {"
      "    label = \"Symbol\";"
      "    : row {"
      "      : button { key = \"col\"; label = \"Solid colour...\"; width = 18; fixed_width = true; }"
      "      : image { key = \"sw\"; width = 6; height = 1.5; fixed_width = true; fixed_height = true; color = 1; }"
      "      : text { key = \"coltxt\"; width = 30; }"
      "    }"
      (strcat "    : edit_box { key = \"dept\"; label = \"Department text:\"; " (ach:dcl-ew 24) "}")
      (strcat "    : edit_box { key = \"suffix\"; label = \"Weight suffix:\"; " (ach:dcl-ew 12) "}")
      (strcat "    : edit_box { key = \"scale\"; label = \"Symbol scale (1 = drawn size):\"; " (ach:dcl-ew 12) "}")
      "  }"
      "  : boxed_column {"
      "    label = \"Rotation  (applied before inserting)\";"
      (strcat "    : edit_box { key = \"rot\"; label = \"Rotate layout about 0,0 (degrees, CCW +):\"; " (ach:dcl-ew 12) "}")
      "    : toggle { key = \"rotsym\"; label = \"Rotate symbols too  (labels stay upright)\"; }"
      "  }"
      "  : row {"
      "    : toggle { key = \"del\"; label = \"Delete hoist inserts from previous runs\"; }"
      "    : text { key = \"delinfo\"; width = 30; }"
      "  }"
      "  ok_cancel;"
      "  errtile;"
      "}")
    (write-line l f))
  (close f)
  path)

(defun ach:dlg-swatch (/ aci)
  (setq aci (cond ((cdr (assoc 62 *ach:dlg-color*))) (7)))
  ;; image tile + fill_image exist on Mac too; guarded so a drawing problem
  ;; there can never stop the dialog (the ACI/RGB text is shown anyway).
  (vl-catch-all-apply
    '(lambda ()
       (start_image "sw")
       (fill_image 0 0 (dimx_tile "sw") (dimy_tile "sw") aci)
       (end_image))
    nil)
  (set_tile "coltxt" (ach:color-text *ach:dlg-color*)))

(defun ach:dlg-pick-color (/ c init)
  (setq init (last *ach:dlg-color*))           ; 62, 420 or 430 pair
  (if (setq c (acad_truecolordlg init nil))
    (progn (setq *ach:dlg-color* c) (ach:dlg-swatch))))

(defun ach:dlg-accept (/ s rot)
  (setq s (atof (get_tile "scale")))
  (setq rot (distof (ach:trim (get_tile "rot")) 2))
  (cond
    ((<= s 0.0) (set_tile "error" "Symbol scale must be greater than 0."))
    ((not rot) (set_tile "error" "Rotation must be a number of degrees, e.g. 0, 90, -90, 180."))
    (T
      (setq *ach:dlg-result*
        (list (vl-remove nil
                (mapcar '(lambda (src i) (if (= (get_tile (strcat "s" (itoa i))) "1") src))
                        *ach:dlg-names* *ach:dlg-idx*))
              *ach:dlg-color*
              (get_tile "dept")
              (get_tile "suffix")
              (= (get_tile "del") "1")
              s
              (mapcar '(lambda (src i)
                         (cons src (nth (atoi (get_tile (strcat "p" (itoa i)))) *ach:side-modes*)))
                      *ach:dlg-names* *ach:dlg-idx*)
              (if (= (get_tile "layout") "lay_tb") "topbottom" "side")
              rot
              (= (get_tile "rotsym") "1")))
      (done_dialog 1))))

;; Returns (singles color dept suffix deleteold scale sides layout
;;          rotation rotate-symbols), nil when cancelled, or the symbol
;; FAILED when load_dialog / new_dialog did not work.
(defun ach:run-dialog (csvpath names meta factor nold / dcl id i e lab res)
  (setq *ach:dlg-names* names
        *ach:dlg-idx* '() *ach:dlg-result* nil)
  (setq i 1)
  (repeat (length names) (setq *ach:dlg-idx* (append *ach:dlg-idx* (list i)) i (1+ i)))
  (setq dcl (ach:write-dcl (length names)))
  (setq id (load_dialog dcl))
  (if (and (>= id 0) (new_dialog "achoists" id))
    (progn
      (set_tile "csv" csvpath)
      (set_tile "info" (strcat "Drawing units: " (ach:unit-name (getvar "INSUNITS"))
                               "  ->  1 m = " (rtos factor 2 4) " units.   "
                               "Labels: auto L/R = mirror the lower-X label of close front/rear pairs."))
      (foreach src names
        (setq i (nth (vl-position src names) *ach:dlg-idx*)
              e (assoc src meta))
        (setq lab (strcat src (if (/= (nth 3 e) "") (strcat "  (" (nth 3 e) ")") "")))
        (if (not (ach:can-single meta src)) (setq lab (strcat lab "  - no single pick")))
        (set_tile (strcat "n" (itoa i)) lab)
        (set_tile (strcat "s" (itoa i)) (if (member src *ach:auto-singles*) "1" "0"))
        (if (not (ach:can-single meta src)) (mode_tile (strcat "s" (itoa i)) 1))
        (start_list (strcat "p" (itoa i)))
        (mapcar 'add_list *ach:side-labels*)
        (end_list)
        (set_tile (strcat "p" (itoa i)) "0"))
      (ach:dlg-swatch)
      (set_tile "dept" *ach:dlg-dept*)
      (set_tile "suffix" *ach:dlg-suffix*)
      (set_tile "scale" (rtos *ach:dlg-scale* 2 3))
      (set_tile "layout" (if (= *ach:dlg-layout* "topbottom") "lay_tb" "lay_side"))
      (set_tile "rot" "0")
      (set_tile "rotsym" "0")
      (set_tile "del" (if (> nold 0) "1" "0"))
      (set_tile "delinfo" (strcat "(" (itoa nold) " found)"))
      (action_tile "col" "(ach:dlg-pick-color)")
      (action_tile "accept" "(ach:dlg-accept)")
      (action_tile "cancel" "(done_dialog 0)")
      (setq res (start_dialog))
      (unload_dialog id)
      (vl-file-delete dcl)
      (if (= res 1) *ach:dlg-result*))
    (progn
      (if (>= id 0) (unload_dialog id))
      (vl-file-delete dcl)
      'failed)))

;;; ===================== command-line prompts (AutoCAD for Mac) ============
(setq *ach:stage* "command-line prompts (AutoCAD for Mac)")
;; Same answers as the dialog, asked on the command line. Every prompt
;; shows its default in <>; Enter keeps it. Used by ACHOISTS on a Mac and by
;; ACHOISTS_CLI everywhere.

;; Sources that hang on one motor in the CSV itself: a single pick and no
;; rear pick (a Soundvision 1-motor source = one "front" row + its "single"
;; twin). ArrayCalc frames always list front + rear, so they stay unticked:
;; the CSV cannot tell whether such a frame is really hung on one point.
(defun ach:auto-singles (rows names meta / rear)
  (foreach r rows
    (if (= (ach:kind r) "rear") (setq rear (cons (ach:get r "source") rear))))
  (vl-remove-if-not '(lambda (s) (and (ach:can-single meta s) (not (member s rear)))) names))

;; Colour name / ACI number -> ACI integer, or nil.
(defun ach:parse-color (s / k)
  (setq k (ach:clean-key s))
  (cond ((= k "") nil)
        ((cdr (assoc k *ach:color-names*)))
        ((and (wcmatch k "#,##,###") (<= 1 (atoi k) 255)) (atoi k))))

;; Colour spec -> what the prompt shows as default: name, number or RGB.
(defun ach:color-label (c / aci nm)
  (setq c (ach:color-spec c))
  (if (and (not (assoc 420 c)) (not (assoc 430 c)) (setq aci (cdr (assoc 62 c))))
    (if (setq nm (car (vl-remove-if-not '(lambda (p) (= (cdr p) aci)) *ach:color-names*)))
      (car nm)
      (itoa aci))
    (ach:color-text c)))

(defun ach:color-names-text ()
  "red, yellow, green, cyan, blue, magenta, white, grey, lightgrey, orange - or a number 1-255 (Dialog opens the colour window)")

(defun ach:ask-color (cur / s n c done)
  (while (not done)
    (setq s (ach:trim (getstring T (strcat "\nSolid colour - name or number 1-255 <"
                                           (ach:color-label cur) ">: "))))
    (cond
      ((= s "") (setq c cur done T))
      ((member (strcase s T) '("dialog" "d"))
       (if (setq n (acad_truecolordlg (last (ach:color-spec cur)) nil))
         (setq c n done T)))
      ((setq n (ach:parse-color s)) (setq c (list (cons 62 n)) done T))
      (T (princ (strcat "\nUnknown colour, try again. Valid: " (ach:color-names-text) ".")))))
  c)

;; Comma/space separated numbers -> list of integers, or nil if any token is bad.
(defun ach:parse-numbers (s / out tok ok)
  (setq ok T)
  (foreach tok (ach:split-list (vl-string-translate " ;" ",," s))
    (if (and (wcmatch tok "#,##,###") (> (atoi tok) 0))
      (setq out (cons (atoi tok) out))
      (setq ok nil)))
  (if ok (reverse out)))

(defun ach:split-list (s / out cur c)
  (setq cur "")
  (foreach c (vl-string->list s)
    (if (= c 44)
      (setq out (cons cur out) cur "")
      (setq cur (strcat cur (chr c)))))
  (vl-remove "" (reverse (cons cur out))))

(defun ach:ask-singles (names meta defaults / i e can s nums bad done res deftxt)
  (princ "\nSources in the CSV:")
  (setq i 1)
  (foreach src names
    (setq e (assoc src meta))
    (princ (strcat "\n  " (itoa i) "  " src
                   (if (/= (nth 3 e) "") (strcat "  (" (nth 3 e) ")") "")
                   (if (ach:can-single meta src) "" "  - no single pick")))
    (setq i (1+ i)))
  (setq can (vl-remove-if-not '(lambda (s) (ach:can-single meta s)) names))
  (if (not can)
    (progn (princ "\nNo source has a single pick: all hoists go on front + rear picks.") nil)
    (progn
      (setq deftxt (if defaults
                     (ach:join (mapcar '(lambda (s) (itoa (1+ (vl-position s names)))) defaults) ",")
                     "none"))
      (while (not done)
        (setq s (ach:trim (getstring T (strcat "\nSingle-point sources - numbers from the list, e.g. 3,4 (0 = none) <"
                                                 deftxt ">: "))))
        (cond
          ((= s "") (setq res defaults done T))
          ((member (strcase s T) '("0" "none" "-")) (setq res nil done T))
          ((not (setq nums (ach:parse-numbers s)))
           (princ "\nType numbers from the list, separated by commas (e.g. 3,4), 0 for none, or Enter for the default."))
          ((setq bad (vl-remove-if '(lambda (n) (and (<= n (length names))
                                                     (ach:can-single meta (nth (1- n) names))))
                                   nums))
           (princ (strcat "\nNot a source with a single pick: "
                          (ach:join (mapcar 'itoa bad) ", ")
                          ". Pick from: "
                          (ach:join (mapcar '(lambda (s) (itoa (1+ (vl-position s names)))) can) ", ")
                          ".")))
          (T (setq res (mapcar '(lambda (n) (nth (1- n) names)) nums) done T))))
      ;; keep the CSV order, like the dialog
      (vl-remove-if-not '(lambda (s) (member s res)) names))))

(defun ach:ask-yesno (msg default / k)
  (initget "Yes No")
  (setq k (getkword (strcat msg " [Yes/No] <" (if default "Yes" "No") ">: ")))
  (cond ((= k "Yes") T) ((= k "No") nil) (T default)))

;; Returns the same list as ach:run-dialog:
;; (singles color dept suffix deleteold scale sides layout rotation rotate-symbols)
(defun ach:run-prompts (csvpath names meta factor nold / singles layout k color dept
                        suffix s scale rot rotsym del)
  (princ (strcat "\nCSV: " csvpath
                 "\nDrawing units: " (ach:unit-name (getvar "INSUNITS"))
                 "  ->  1 m = " (rtos factor 2 4) " units."))
  ;; 1. single-point sources
  (setq singles (ach:ask-singles names meta *ach:auto-singles*))
  ;; 2. label layout
  (initget "Side Topbottom")
  (setq k (getkword (strcat "\nLabels [Side/Topbottom] <"
                            (if (= *ach:dlg-layout* "topbottom") "Topbottom" "Side") ">: ")))
  (setq layout (cond ((= k "Side") "side") ((= k "Topbottom") "topbottom") (T *ach:dlg-layout*)))
  ;; 3. colour
  (setq color (ach:ask-color *ach:dlg-color*))
  ;; 4. texts
  (setq s (getstring T (strcat "\nDepartment text <" *ach:dlg-dept* ">: ")))
  (setq dept (if (= (ach:trim s) "") *ach:dlg-dept* s))
  ;; AutoCAD drops leading spaces from typed input, so quotes keep them: " kg"
  (setq s (getstring T (strcat "\nWeight suffix after the kg number, quote it to keep spaces <\""
                               *ach:dlg-suffix* "\">: ")))
  (setq suffix (cond ((= s "") *ach:dlg-suffix*)
                     ((and (> (strlen s) 1) (= (substr s 1 1) "\"")
                           (= (substr s (strlen s)) "\""))
                      (substr s 2 (- (strlen s) 2)))
                     (T s)))
  ;; 5. symbol scale (> 0)
  (initget 6)
  (setq scale (getreal (strcat "\nSymbol scale, 1 = drawn size <" (rtos *ach:dlg-scale* 2 3) ">: ")))
  (if (not scale) (setq scale *ach:dlg-scale*))
  ;; 6. rotation
  (setq rot (getreal "\nRotate layout about 0,0 - degrees, CCW + <0>: "))
  (if (not rot) (setq rot 0.0))
  (setq rotsym (if (equal rot 0.0 1e-9)
                 nil
                 (ach:ask-yesno "\nRotate symbols too (labels stay upright)?" nil)))
  ;; 7. earlier hoists
  (setq del (if (> nold 0)
              (ach:ask-yesno (strcat "\nDelete " (itoa nold) " hoist insert(s) from previous runs?") T)
              nil))
  (list singles color dept suffix del scale
        (mapcar '(lambda (src) (cons src "default")) names)
        layout (float rot) rotsym))

;;; ========================= interactive command ===========================
(setq *ach:stage* "interactive command")

(setq *ach:auto-singles* nil)

;; Command-line CSV path (used when FILEDIA = 0 in prompt mode).
(defun ach:ask-path (start / p)
  (if (and start (not (findfile start))) (setq start nil))
  (setq p (getstring T (strcat "\nCSV file path"
                               (if start (strcat " <" start ">") "") ": ")))
  (setq p (vl-string-trim " \t\"" p))
  (cond
    ((= p "") start)
    ((findfile p))
    ((findfile (strcat p ".csv")))
    (T (princ (strcat "\nFile not found: " p)) nil)))

;; UI = "dialog" (DCL) or "prompts" (command line).
(defun ach:command (ui / *error* csv data rows names meta factor u res r nold
                     doc bname bfile old-cmdecho start s)
  (setq old-cmdecho (getvar "CMDECHO"))
  (defun *error* (m)
    (setvar "CMDECHO" old-cmdecho)
    (if (not (member m '("Function cancelled" "quit / exit abort")))
      (princ (strcat "\nACHOISTS error: " m)))
    (princ))
  (setvar "CMDECHO" 0)
  (setq *ach:eng* (ach:engine nil))
  (if (ach:ax-p) (setq doc (vla-get-ActiveDocument (vlax-get-acad-object))))

  ;; remembered settings
  (setq *ach:dlg-dept*   (cond ((getenv "ACHOISTS_Dept")) (*ach:default-dept*)))
  (setq *ach:dlg-suffix* (cond ((getenv "ACHOISTS_Suffix")) (*ach:default-suffix*)))
  (setq s (getenv "ACHOISTS_Scale"))
  (setq *ach:dlg-scale*  (if (and s (> (atof s) 0.0)) (atof s) *ach:symbol-scale*))
  (setq s (getenv "ACHOISTS_Color"))
  (setq *ach:dlg-color*  (if (and s (/= s ""))
                           (ach:color-spec (vl-catch-all-apply 'read (list s)))
                           *ach:default-color*))
  (if (vl-catch-all-error-p *ach:dlg-color*) (setq *ach:dlg-color* *ach:default-color*))
  (setq *ach:dlg-layout* (ach:norm-layout (cond ((getenv "ACHOISTS_Layout")) (*ach:label-layout*))))

  ;; 1. CSV - start in the drawing's folder (or the last CSV's folder)
  (setq start (getenv "ACHOISTS_LastCSV"))
  (if (not (and start (findfile start))) (setq start (getvar "DWGPREFIX")))
  (setq csv
    (if (and (= ui "prompts") (= (getvar "FILEDIA") 0))
      ;; FILEDIA 0 + prompt mode: type the path (AutoCAD convention)
      (ach:ask-path start)
      (getfiled "ArrayCalc hoist CSV" start "csv" 0)))
  (cond
    ((not csv) (princ "\nACHOISTS: cancelled."))
    ((not (setq data (ach:read-csv csv))) (alert (strcat "Cannot read CSV:\n" csv)))
    ((null (setq rows (cadr data))) (alert "The CSV has no data rows."))
    (T
     (setenv "ACHOISTS_LastCSV" csv)
     (setq data (ach:sources rows) names (car data) meta (cadr data))
     (setq *ach:auto-singles* (ach:auto-singles rows names meta))
     ;; 2. units
     (setq factor (ach:factor-from-insunits))
     (if (not factor)
       (progn
         ;; Ask only - this tool never changes INSUNITS in the drawing.
         (initget "Millimeters Centimeters meTers Inches Feet")
         (setq u (getkword "\nDrawing is unitless (INSUNITS=0). One drawing unit is [Millimeters/Centimeters/meTers/Inches/Feet] <Millimeters>: "))
         (setq factor (cdr (assoc (if u u "Millimeters")
                                  '(("Millimeters" . 1000.0) ("Centimeters" . 100.0)
                                    ("meTers" . 1.0) ("Inches" . 39.37007874015748)
                                    ("Feet" . 3.280839895013123)))))))
     ;; 3. block present? else find / ask for the block DWG
     (setq bname (ach:x-find-block doc))
     (if (not bname)
       (progn
         (setq bfile (ach:find-block-file csv))
         (if (not bfile)
           (setq bfile (getfiled (strcat "Hoist block DWG (" *ach:block-file* ")")
                                 (getvar "DWGPREFIX") "dwg" 0)))))
     (if (and (not bname) (not bfile))
       (princ "\nACHOISTS: no hoist block - cancelled.")
       (progn
         (setq nold (length (ach:x-previous-inserts (cond (bname) (*ach:block-name*)))))
         ;; 4. dialog / command-line prompts
         (setq res (if (= ui "prompts")
                     (ach:run-prompts csv names meta factor nold)
                     (ach:run-dialog csv names meta factor nold)))
         (if (eq res 'failed)
           (if (or (ach:mac-p) (not (ach:activex-p)))
             ;; Mac: no dialog -> the same questions on the command line
             (progn
               (princ "\nACHOISTS: the dialog could not be loaded - using command-line prompts.")
               (setq ui "prompts"
                     res (ach:run-prompts csv names meta factor nold)))
             (progn (alert "ACHOISTS: could not load the dialog.") (setq res nil))))
         (if (not res)
           (princ "\nACHOISTS: cancelled.")
           (progn
             (setq *ach:dlg-color* (nth 1 res))
             (setenv "ACHOISTS_Dept"   (nth 2 res))
             (setenv "ACHOISTS_Suffix" (nth 3 res))
             (setenv "ACHOISTS_Scale"  (rtos (nth 5 res) 2 4))
             (setenv "ACHOISTS_Color"  (vl-prin1-to-string (nth 1 res)))
             (setenv "ACHOISTS_Layout" (nth 7 res))
             ;; 5. place
             (setq r (achoists-run-ex csv (nth 0 res) (nth 1 res) (nth 2 res) (nth 3 res)
                                      (nth 4 res)
                                      (list (cons "factor" factor)
                                            (cons "scale" (nth 5 res))
                                            (cons "sides" (nth 6 res))
                                            (cons "layout" (nth 7 res))
                                            (cons "rotation" (nth 8 res))
                                            (cons "rotate-symbols" (nth 9 res))
                                            (cons "blockfile" bfile)
                                            (cons "engine" *ach:eng*))))
             (if (= ui "prompts")
               (princ (strcat (if (car r) "\n\nACHOISTS done\n" "\n\nACHOISTS - nothing placed\n")
                              (cdr r)))
               (alert (strcat (if (car r) "ACHOISTS done\n\n" "ACHOISTS - nothing placed\n\n")
                              (cdr r))))))))))
  (setvar "CMDECHO" old-cmdecho)
  (princ))

;; Everything loaded: the commands defined at the top can now run.
(setq *ach:loaded* T *ach:stage* "done")
(princ (strcat "\nACHOISTS loaded (" (if (ach:mac-p) "Mac" "Windows") ")"
               " - type ACHOISTS (or ACHOISTS_CLI for command-line prompts)."))
(princ)
